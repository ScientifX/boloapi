"""
Link Validation Service
Extracts and validates all URLs from FBI BOLO data records.
"""
import re
import json
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import httpx
import psycopg2
from psycopg2.extras import execute_values
from psycopg2.extensions import connection as Connection
from contextlib import contextmanager

from config import DB_CONFIG

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URL validation regex pattern
# Matches http:// or https:// followed by valid URL characters
URL_PATTERN = re.compile(
    r'^https?://'  # http:// or https://
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain
    r'localhost|'  # localhost
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # or IP
    r'(?::\d+)?'  # optional port
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

# Request timeout in seconds
REQUEST_TIMEOUT = 12.0

# Concurrent request limit (be nice to FBI servers)
MAX_CONCURRENT_REQUESTS = 5

# Delay between individual requests (seconds)
REQUEST_DELAY = 0.2

# Delay between batches (seconds)
BATCH_DELAY = 2.0

# Retry settings for 429 (Too Many Requests)
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5.0  # Base seconds to wait on 429

# Browser-like headers to avoid 403 blocks
BROWSER_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Cache-Control': 'max-age=0',
    'Referer': 'https://www.fbi.gov/',
    'Origin': 'https://www.fbi.gov'
}

# Headers specifically for image requests
IMAGE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'image',
    'Sec-Fetch-Mode': 'no-cors',
    'Sec-Fetch-Site': 'same-origin',
    'Referer': 'https://www.fbi.gov/',
    'Origin': 'https://www.fbi.gov'
}


def get_headers_for_url(url: str) -> dict:
    """
    Return appropriate headers based on URL type.
    Images need different Accept and Sec-Fetch-Dest headers.
    """
    url_lower = url.lower()
    
    # Check if it's an image URL
    if ('@@images' in url_lower or 
        url_lower.endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico'))):
        return IMAGE_HEADERS
    
    return BROWSER_HEADERS


def should_skip_url(url: str) -> bool:
    """
    Check if a URL should be skipped because it's known to be blocked by FBI bot protection.
    
    These URLs return 403 from automated requests but work fine in browsers.
    They're not broken - just protected.
    
    Skipped patterns:
    - @@images/ paths (Plone CMS scaled images)
    - www.fbi.gov HTML pages (no file extension)
    
    Allowed patterns:
    - Direct files (.pdf, .jpg, .png, etc.)
    - api.fbi.gov endpoints
    - @@download/ paths
    """
    url_lower = url.lower()
    
    # Always skip @@images/ paths - these are Plone scaled images that block bots
    if '@@images' in url_lower:
        return True
    
    # Check if it's a www.fbi.gov URL
    if 'www.fbi.gov' in url_lower:
        # Allow direct file downloads
        allowed_extensions = (
            '.pdf', '.jpg', '.jpeg', '.png', '.gif', '.webp', 
            '.svg', '.ico', '.doc', '.docx', '.xls', '.xlsx'
        )
        if url_lower.endswith(allowed_extensions):
            return False
        
        # Allow @@download paths
        if '@@download' in url_lower:
            return False
        
        # Skip HTML pages (no extension = likely blocked)
        # These are paths like /wanted/cyber/zhou-shuai
        return True
    
    # Allow everything else (api.fbi.gov, other domains)
    return False


def filter_urls_for_validation(urls: List[Tuple[str, str, str]]) -> Tuple[List[Tuple[str, str, str]], int]:
    """
    Filter out URLs that are known to be blocked by bot protection.
    
    Args:
        urls: List of (uid, field, url) tuples
        
    Returns:
        Tuple of (filtered_urls, skipped_count)
    """
    filtered = []
    skipped = 0
    
    for uid, field, url in urls:
        if should_skip_url(url):
            skipped += 1
        else:
            filtered.append((uid, field, url))
    
    if skipped > 0:
        logger.info(f"Filtered out {skipped} URLs known to be blocked by bot protection")
    
    return filtered, skipped


@contextmanager
def get_db_connection():
    """Context manager for database connections"""
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        yield conn
    except Exception as e:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()


def is_valid_url(url: Any) -> bool:
    """
    Validate that a value is a properly formatted URL.
    
    Args:
        url: Value to validate
        
    Returns:
        True if valid URL, False otherwise
    """
    if not url:
        return False
    if not isinstance(url, str):
        return False
    return URL_PATTERN.match(url) is not None


def extract_urls_from_record(item: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Extract all URLs from a single BOLO record.
    
    Args:
        item: Raw JSON record from FBI API
        
    Returns:
        List of tuples: (uid, field_name, url)
    """
    urls = []
    uid = item.get('uid')
    
    if not uid:
        return urls
    
    # 1. pathId - direct URL field
    path_id = item.get('pathId')
    if is_valid_url(path_id):
        urls.append((uid, 'path_id', path_id))
    
    # 2. url - direct URL field
    url = item.get('url')
    if is_valid_url(url):
        urls.append((uid, 'url', url))
    
    # 3. files[].url - array of file objects
    files = item.get('files') or []
    for idx, file_obj in enumerate(files):
        if isinstance(file_obj, dict):
            file_url = file_obj.get('url')
            if is_valid_url(file_url):
                urls.append((uid, f'files_{idx}_url', file_url))
    
    # 4. images[] - array of image objects with large, thumb, original
    images = item.get('images') or []
    for idx, image_obj in enumerate(images):
        if isinstance(image_obj, dict):
            # large
            large_url = image_obj.get('large')
            if is_valid_url(large_url):
                urls.append((uid, f'images_{idx}_large', large_url))
            
            # thumb
            thumb_url = image_obj.get('thumb')
            if is_valid_url(thumb_url):
                urls.append((uid, f'images_{idx}_thumb', thumb_url))
            
            # original
            original_url = image_obj.get('original')
            if is_valid_url(original_url):
                urls.append((uid, f'images_{idx}_original', original_url))
    
    return urls


def extract_all_urls_from_data(data: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Extract all URLs from the full FBI API response data.
    
    Args:
        data: Full JSON response with 'items' array
        
    Returns:
        List of tuples: (uid, field_name, url)
    """
    all_urls = []
    items = data.get('items', [])
    
    for item in items:
        urls = extract_urls_from_record(item)
        all_urls.extend(urls)
    
    logger.info(f"Extracted {len(all_urls)} URLs from {len(items)} records")
    return all_urls


async def validate_single_url(
    client: httpx.AsyncClient, 
    uid: str, 
    field: str, 
    url: str
) -> Dict[str, Any]:
    """
    Validate a single URL using GET request with browser headers.
    Includes retry logic for 429 (Too Many Requests) responses.
    
    Args:
        client: HTTP client
        uid: BOLO record UID
        field: Field name where URL was found
        url: URL to validate
        
    Returns:
        Dict with validation results
    """
    result = {
        'uid': uid,
        'field': field,
        'actual_url': url,
        'result': 'failure',
        'response_code': None
    }
    
    # Get appropriate headers for this URL type
    headers = get_headers_for_url(url)
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            # Small delay between requests to be polite
            if attempt == 0:
                await asyncio.sleep(REQUEST_DELAY)
            
            # Use GET request with stream=True to avoid downloading full content
            # HEAD requests are often blocked by servers
            async with client.stream('GET', url, headers=headers) as response:
                result['response_code'] = response.status_code
                
                # Handle rate limiting (429)
                if response.status_code == 429:
                    if attempt < MAX_RETRIES:
                        # Exponential backoff: 5s, 10s, 20s
                        wait_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.info(f"Rate limited (429), waiting {wait_time}s before retry {attempt + 1}/{MAX_RETRIES}")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        result['result'] = 'failure'
                        logger.warning(f"Max retries exceeded for {url}")
                        break
                
                if 200 <= response.status_code < 400:
                    result['result'] = 'success'
                else:
                    result['result'] = 'failure'
                
                # Success or non-429 failure, exit retry loop
                break
                
        except httpx.TimeoutException:
            result['result'] = 'timeout'
            logger.debug(f"Timeout validating URL: {url}")
            break
            
        except httpx.RequestError as e:
            result['result'] = 'failure'
            logger.debug(f"Request error validating URL {url}: {str(e)}")
            break
            
        except Exception as e:
            result['result'] = 'failure'
            logger.warning(f"Unexpected error validating URL {url}: {str(e)}")
            break
    
    return result


async def validate_urls_batch(
    urls: List[Tuple[str, str, str]],
    max_concurrent: int = MAX_CONCURRENT_REQUESTS
) -> List[Dict[str, Any]]:
    """
    Validate multiple URLs concurrently with rate limiting.
    
    Args:
        urls: List of (uid, field, url) tuples
        max_concurrent: Maximum concurrent requests
        
    Returns:
        List of validation result dicts
    """
    results = []
    semaphore = asyncio.Semaphore(max_concurrent)
    start_time = datetime.now()
    
    async def validate_with_semaphore(client, uid, field, url):
        async with semaphore:
            return await validate_single_url(client, uid, field, url)
    
    # Create client (headers are passed per-request based on URL type)
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True
    ) as client:
        tasks = [
            validate_with_semaphore(client, uid, field, url)
            for uid, field, url in urls
        ]
        
        # Process in batches for progress logging and rate limiting
        batch_size = 50  # Smaller batches
        total_batches = (len(tasks) + batch_size - 1) // batch_size
        
        for batch_num, i in enumerate(range(0, len(tasks), batch_size), 1):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            # Count results
            success_count = 0
            failure_count = 0
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch validation error: {str(result)}")
                    failure_count += 1
                else:
                    results.append(result)
                    if result.get('result') == 'success':
                        success_count += 1
                    else:
                        failure_count += 1
            
            # Progress logging with ETA
            completed = min(i + batch_size, len(tasks))
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = completed / elapsed if elapsed > 0 else 0
            remaining = len(tasks) - completed
            eta_seconds = remaining / rate if rate > 0 else 0
            eta_minutes = eta_seconds / 60
            
            logger.info(
                f"Batch {batch_num}/{total_batches}: {completed}/{len(tasks)} URLs "
                f"({success_count} ok, {failure_count} failed) - ETA: {eta_minutes:.1f} min"
            )
            
            # Delay between batches to avoid overwhelming the server
            if i + batch_size < len(tasks):
                await asyncio.sleep(BATCH_DELAY)
    
    return results


def save_validation_results(conn: Connection, results: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Save validation results to database using MERGE (INSERT ON CONFLICT UPDATE).
    
    Args:
        conn: Database connection
        results: List of validation result dicts
        
    Returns:
        Dict with counts: inserted, updated
    """
    if not results:
        return {'inserted': 0, 'updated': 0}
    
    # Prepare values for batch upsert
    values = [
        (
            r['uid'],
            r['field'],
            r['actual_url'],
            r['result'],
            r['response_code']
        )
        for r in results
    ]
    
    with conn.cursor() as cur:
        # UPSERT query - insert new, update existing
        upsert_query = """
            INSERT INTO tbl_bolo_link_check (
                uid, field, actual_url, result, response_code, updated_at
            )
            VALUES %s
            ON CONFLICT (uid, field, actual_url)
            DO UPDATE SET
                result = EXCLUDED.result,
                response_code = EXCLUDED.response_code,
                updated_at = NOW()
            RETURNING (xmax = 0) as is_insert
        """
        
        # Execute batch upsert
        results_returned = execute_values(
            cur,
            upsert_query,
            values,
            template="(%s, %s, %s, %s, %s, NOW())",
            page_size=100,
            fetch=True
        )
        
        # Count inserts vs updates
        insert_count = sum(1 for r in results_returned if r[0])
        update_count = sum(1 for r in results_returned if not r[0])
        
        logger.info(f"Link check UPSERT: {insert_count} inserted, {update_count} updated")
        
        return {
            'inserted': insert_count,
            'updated': update_count
        }


async def validate_links_from_file(file_path: str) -> Dict[str, Any]:
    """
    Main function to validate all links from a JSON data file.
    
    Args:
        file_path: Path to the FBI API JSON data file
        
    Returns:
        Dict with validation summary
    """
    start_time = datetime.now()
    
    # Load JSON data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading JSON file: {str(e)}")
        raise
    
    # Extract all URLs
    all_urls = extract_all_urls_from_data(data)
    
    if not all_urls:
        return {
            'status': 'success',
            'message': 'No URLs found to validate',
            'total_urls': 0,
            'processing_time_seconds': 0
        }
    
    # Filter out URLs known to be blocked by bot protection
    urls, skipped_count = filter_urls_for_validation(all_urls)
    
    if not urls:
        return {
            'status': 'success',
            'message': 'All URLs filtered (known bot-protected paths)',
            'total_urls_extracted': len(all_urls),
            'urls_skipped_bot_protection': skipped_count,
            'urls_validated': 0,
            'processing_time_seconds': 0
        }
    
    # Validate URLs asynchronously
    logger.info(f"Starting validation of {len(urls)} URLs ({skipped_count} skipped as bot-protected)")
    validation_results = await validate_urls_batch(urls)
    
    # Save results to database
    with get_db_connection() as conn:
        db_results = save_validation_results(conn, validation_results)
        conn.commit()
    
    # Calculate summary statistics
    processing_time = (datetime.now() - start_time).total_seconds()
    
    success_count = sum(1 for r in validation_results if r['result'] == 'success')
    failure_count = sum(1 for r in validation_results if r['result'] == 'failure')
    timeout_count = sum(1 for r in validation_results if r['result'] == 'timeout')
    
    # Count by response code
    response_codes = {}
    for r in validation_results:
        code = r['response_code']
        if code:
            response_codes[code] = response_codes.get(code, 0) + 1
    
    summary = {
        'status': 'success',
        'total_urls_extracted': len(all_urls),
        'urls_skipped_bot_protection': skipped_count,
        'urls_validated': len(urls),
        'total_records': len(data.get('items', [])),
        'results': {
            'success': success_count,
            'failure': failure_count,
            'timeout': timeout_count
        },
        'database': {
            'inserted': db_results['inserted'],
            'updated': db_results['updated']
        },
        'response_codes': dict(sorted(response_codes.items())),
        'processing_time_seconds': round(processing_time, 2)
    }
    
    logger.info(f"Link validation complete: {summary}")
    return summary


def get_link_check_summary(conn: Connection) -> Dict[str, Any]:
    """
    Get summary statistics from tbl_bolo_link_check.
    
    Args:
        conn: Database connection
        
    Returns:
        Dict with summary statistics
    """
    with conn.cursor() as cur:
        # Overall counts by result
        cur.execute("""
            SELECT 
                result,
                COUNT(*) as count
            FROM tbl_bolo_link_check
            GROUP BY result
            ORDER BY result
        """)
        result_counts = {row[0]: row[1] for row in cur.fetchall()}
        
        # Counts by response code
        cur.execute("""
            SELECT 
                response_code,
                COUNT(*) as count
            FROM tbl_bolo_link_check
            WHERE response_code IS NOT NULL
            GROUP BY response_code
            ORDER BY response_code
        """)
        code_counts = {row[0]: row[1] for row in cur.fetchall()}
        
        # Counts by field type
        cur.execute("""
            SELECT 
                CASE 
                    WHEN field LIKE 'images_%' THEN 'images'
                    WHEN field LIKE 'files_%' THEN 'files'
                    ELSE field
                END as field_type,
                COUNT(*) as count
            FROM tbl_bolo_link_check
            GROUP BY field_type
            ORDER BY field_type
        """)
        field_counts = {row[0]: row[1] for row in cur.fetchall()}
        
        # Total unique UIDs
        cur.execute("SELECT COUNT(DISTINCT uid) FROM tbl_bolo_link_check")
        unique_uids = cur.fetchone()[0]
        
        # Last updated
        cur.execute("SELECT MAX(updated_at) FROM tbl_bolo_link_check")
        last_updated = cur.fetchone()[0]
        
        return {
            'total_links': sum(result_counts.values()),
            'unique_records': unique_uids,
            'by_result': result_counts,
            'by_response_code': code_counts,
            'by_field_type': field_counts,
            'last_updated': str(last_updated) if last_updated else None
        }


def get_failed_links(
    conn: Connection, 
    limit: int = 100,
    include_timeouts: bool = True
) -> List[Dict[str, Any]]:
    """
    Get list of failed/timeout links for review.
    
    Args:
        conn: Database connection
        limit: Maximum number of results
        include_timeouts: Include timeout results
        
    Returns:
        List of failed link records
    """
    results_filter = "('failure', 'timeout')" if include_timeouts else "('failure')"
    
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT 
                lc.uid,
                lc.field,
                lc.actual_url,
                lc.result,
                lc.response_code,
                lc.updated_at,
                b.title
            FROM tbl_bolo_link_check lc
            LEFT JOIN tbl_bolo b ON lc.uid = b.uid AND b.is_active = TRUE
            WHERE lc.result IN {results_filter}
            ORDER BY lc.updated_at DESC
            LIMIT %s
        """, (limit,))
        
        columns = ['uid', 'field', 'actual_url', 'result', 'response_code', 'updated_at', 'title']
        return [dict(zip(columns, row)) for row in cur.fetchall()]