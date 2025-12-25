"""
Link Validation and File Caching Service
=========================================
Extracts and validates all URLs from FBI BoloDoc data records.
Downloads and caches files for archive generation.
Creates ZIP archives for premium annual subscribers.

Features:
- URL extraction from BOLO records (pathId, url, files[], images[])
- Async URL validation with rate limiting
- File download caching (download once, reuse from disk)
- ZIP archive generation with per-person folders
- info.txt summary per person
- Root manifest.txt with statistics
"""
import re
import os
import json
import logging
import asyncio
import hashlib
import shutil
import zipfile
from typing import List, Dict, Any, Optional, Tuple, Set
from datetime import datetime
from pathlib import Path
from collections import defaultdict

import httpx
import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2.extensions import connection as Connection
from contextlib import contextmanager

from config import DB_CONFIG

# =============================================================================
# CONFIGURATION
# =============================================================================

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Directory paths
DATA_DIR = Path("data")
CACHE_DIR = DATA_DIR / "bolo_cache"
ARCHIVE_PATH = DATA_DIR / "bolodoc_files.zip"

# URL validation regex pattern
URL_PATTERN = re.compile(
    r'^https?://'
    r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'
    r'localhost|'
    r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'
    r'(?::\d+)?'
    r'(?:/?|[/?]\S+)$', re.IGNORECASE
)

# Request settings
REQUEST_TIMEOUT = 30.0  # Increased for file downloads
MAX_CONCURRENT_REQUESTS = 5
REQUEST_DELAY = 0.2
BATCH_DELAY = 2.0
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 5.0

# Browser-like headers
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

# Headers for file downloads
DOWNLOAD_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': '*/*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Referer': 'https://www.fbi.gov/',
}


# =============================================================================
# DATABASE UTILITIES
# =============================================================================

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


# =============================================================================
# URL UTILITIES
# =============================================================================

def is_valid_url(url: Any) -> bool:
    """Validate that a value is a properly formatted URL."""
    if not url:
        return False
    if not isinstance(url, str):
        return False
    return URL_PATTERN.match(url) is not None


def is_plone_url(url: str) -> bool:
    """
    Check if URL is a Plone CMS image URL that blocks bot requests.
    These return 403 from automated requests but work in browsers.
    """
    url_lower = url.lower()
    return '@@images' in url_lower


def get_url_hash(url: str) -> str:
    """Generate MD5 hash of URL for cache filename."""
    return hashlib.md5(url.encode('utf-8')).hexdigest()


def get_extension_from_url(url: str) -> str:
    """Extract file extension from URL."""
    # Remove query string
    clean_url = url.split('?')[0]
    
    # Get extension
    ext = Path(clean_url).suffix.lower()
    
    # Default to .bin if no extension found
    if not ext or len(ext) > 10:
        return '.bin'
    
    return ext


def get_cache_filename(url: str) -> str:
    """Generate unique cache filename from URL."""
    url_hash = get_url_hash(url)
    ext = get_extension_from_url(url)
    return f"{url_hash}{ext}"


def sanitize_folder_name(name: str) -> str:
    """
    Sanitize a string for use as a folder name.
    Removes/replaces invalid characters.
    """
    if not name:
        return "UNKNOWN"
    
    # Replace problematic characters
    sanitized = re.sub(r'[<>:"/\\|?*]', '', name)
    sanitized = re.sub(r'\s+', '_', sanitized)
    sanitized = sanitized.strip('._')
    
    # Limit length
    if len(sanitized) > 50:
        sanitized = sanitized[:50]
    
    return sanitized.upper() if sanitized else "UNKNOWN"


# =============================================================================
# URL EXTRACTION
# =============================================================================

def extract_urls_from_record(item: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Extract all URLs from a single BOLO record.
    
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


# =============================================================================
# CACHE MANAGEMENT
# =============================================================================

def ensure_cache_dir() -> Path:
    """Create cache directory if it doesn't exist."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR


def get_cached_file_path(url: str) -> Optional[Path]:
    """
    Get path to cached file if it exists.
    Returns None if not cached.
    """
    filename = get_cache_filename(url)
    cache_path = CACHE_DIR / filename
    
    if cache_path.exists():
        return cache_path
    return None


def save_to_cache(url: str, content: bytes) -> Path:
    """
    Save downloaded content to cache.
    Returns path to cached file.
    """
    ensure_cache_dir()
    filename = get_cache_filename(url)
    cache_path = CACHE_DIR / filename
    
    with open(cache_path, 'wb') as f:
        f.write(content)
    
    return cache_path


def clear_cache() -> Dict[str, Any]:
    """
    Delete all cached files.
    Returns statistics about deleted files.
    """
    if not CACHE_DIR.exists():
        return {"files_deleted": 0, "bytes_freed": 0}
    
    files_deleted = 0
    bytes_freed = 0
    
    for file_path in CACHE_DIR.iterdir():
        if file_path.is_file():
            bytes_freed += file_path.stat().st_size
            file_path.unlink()
            files_deleted += 1
    
    return {
        "files_deleted": files_deleted,
        "bytes_freed": bytes_freed,
        "bytes_freed_mb": round(bytes_freed / (1024 * 1024), 2)
    }


def get_cache_stats() -> Dict[str, Any]:
    """Get statistics about the cache directory."""
    if not CACHE_DIR.exists():
        return {
            "exists": False,
            "file_count": 0,
            "total_size_bytes": 0,
            "total_size_mb": 0
        }
    
    file_count = 0
    total_size = 0
    extensions = defaultdict(int)
    
    for file_path in CACHE_DIR.iterdir():
        if file_path.is_file():
            file_count += 1
            total_size += file_path.stat().st_size
            ext = file_path.suffix.lower() or '.unknown'
            extensions[ext] += 1
    
    return {
        "exists": True,
        "path": str(CACHE_DIR),
        "file_count": file_count,
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "files_by_extension": dict(extensions)
    }


# =============================================================================
# URL VALIDATION (HEAD/GET requests without downloading)
# =============================================================================

async def validate_single_url(
    client: httpx.AsyncClient,
    uid: str,
    field: str,
    url: str
) -> Dict[str, Any]:
    """
    Validate a single URL using GET request (streaming, no full download).
    Marks Plone URLs as 'plone_blocked' without attempting request.
    """
    result = {
        'uid': uid,
        'field': field,
        'actual_url': url,
        'result': 'failure',
        'response_code': None,
        'content_type': None,
        'is_plone': False
    }
    
    # Check for Plone URLs - mark but don't request
    if is_plone_url(url):
        result['result'] = 'plone_blocked'
        result['is_plone'] = True
        result['response_code'] = 403  # Expected behavior
        logger.debug(f"Plone URL skipped: {url}")
        return result
    
    for attempt in range(MAX_RETRIES + 1):
        try:
            if attempt == 0:
                await asyncio.sleep(REQUEST_DELAY)
            
            async with client.stream('GET', url, headers=BROWSER_HEADERS) as response:
                result['response_code'] = response.status_code
                result['content_type'] = response.headers.get('content-type', '')
                
                if response.status_code == 429:
                    if attempt < MAX_RETRIES:
                        wait_time = RETRY_BACKOFF_BASE * (2 ** attempt)
                        logger.info(f"Rate limited (429), waiting {wait_time}s")
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        result['result'] = 'rate_limited'
                        break
                
                if 200 <= response.status_code < 400:
                    result['result'] = 'success'
                else:
                    result['result'] = 'failure'
                break
                
        except httpx.TimeoutException:
            result['result'] = 'timeout'
            break
        except httpx.RequestError as e:
            result['result'] = 'failure'
            logger.debug(f"Request error: {url}: {str(e)}")
            break
        except Exception as e:
            result['result'] = 'failure'
            logger.warning(f"Unexpected error: {url}: {str(e)}")
            break
    
    return result


async def validate_urls_batch(
    urls: List[Tuple[str, str, str]],
    max_concurrent: int = MAX_CONCURRENT_REQUESTS
) -> List[Dict[str, Any]]:
    """Validate multiple URLs concurrently with rate limiting."""
    results = []
    semaphore = asyncio.Semaphore(max_concurrent)
    start_time = datetime.now()
    
    async def validate_with_semaphore(client, uid, field, url):
        async with semaphore:
            return await validate_single_url(client, uid, field, url)
    
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True
    ) as client:
        tasks = [
            validate_with_semaphore(client, uid, field, url)
            for uid, field, url in urls
        ]
        
        batch_size = 50
        total_batches = (len(tasks) + batch_size - 1) // batch_size
        
        for batch_num, i in enumerate(range(0, len(tasks), batch_size), 1):
            batch = tasks[i:i + batch_size]
            batch_results = await asyncio.gather(*batch, return_exceptions=True)
            
            success_count = 0
            for result in batch_results:
                if isinstance(result, Exception):
                    logger.error(f"Batch error: {str(result)}")
                else:
                    results.append(result)
                    if result.get('result') == 'success':
                        success_count += 1
            
            completed = min(i + batch_size, len(tasks))
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = completed / elapsed if elapsed > 0 else 0
            remaining = len(tasks) - completed
            eta_minutes = (remaining / rate / 60) if rate > 0 else 0
            
            logger.info(
                f"Batch {batch_num}/{total_batches}: {completed}/{len(tasks)} "
                f"({success_count} ok) - ETA: {eta_minutes:.1f} min"
            )
            
            if i + batch_size < len(tasks):
                await asyncio.sleep(BATCH_DELAY)
    
    return results


# =============================================================================
# FILE DOWNLOADING WITH CACHING
# =============================================================================

async def download_file_with_cache(
    client: httpx.AsyncClient,
    url: str,
    validated_urls: Set[str]
) -> Dict[str, Any]:
    """
    Download a file, using cache if available.
    
    Args:
        client: HTTP client
        url: URL to download
        validated_urls: Set of URLs known to return 200
        
    Returns:
        Dict with download result and file info
    """
    result = {
        'url': url,
        'from_cache': False,
        'success': False,
        'cache_path': None,
        'file_size': 0,
        'content_type': None,
        'error': None
    }
    
    # Skip Plone URLs
    if is_plone_url(url):
        result['error'] = 'plone_blocked'
        return result
    
    # Check cache first
    cached_path = get_cached_file_path(url)
    if cached_path and url in validated_urls:
        result['from_cache'] = True
        result['success'] = True
        result['cache_path'] = str(cached_path.relative_to(DATA_DIR))
        result['file_size'] = cached_path.stat().st_size
        return result
    
    # Download file
    try:
        response = await client.get(url, headers=DOWNLOAD_HEADERS)
        
        if response.status_code == 200:
            content = response.content
            cache_path = save_to_cache(url, content)
            
            result['success'] = True
            result['cache_path'] = str(cache_path.relative_to(DATA_DIR))
            result['file_size'] = len(content)
            result['content_type'] = response.headers.get('content-type', '')
        else:
            result['error'] = f"HTTP {response.status_code}"
            
    except httpx.TimeoutException:
        result['error'] = 'timeout'
    except Exception as e:
        result['error'] = str(e)
    
    return result


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def save_validation_results(conn: Connection, results: List[Dict[str, Any]]) -> Dict[str, int]:
    """Save validation results to database using UPSERT."""
    if not results:
        return {'inserted': 0, 'updated': 0}
    
    values = []
    for r in results:
        values.append((
            r['uid'],
            r['field'],
            r['actual_url'],
            r['result'],
            r['response_code'],
            r.get('content_type')
        ))
    
    with conn.cursor() as cur:
        upsert_query = """
            INSERT INTO tbl_bolo_link_check (
                uid, field, actual_url, result, response_code, content_type, updated_at
            )
            VALUES %s
            ON CONFLICT (uid, field, actual_url)
            DO UPDATE SET
                result = EXCLUDED.result,
                response_code = EXCLUDED.response_code,
                content_type = EXCLUDED.content_type,
                updated_at = NOW()
            RETURNING (xmax = 0) as is_insert
        """
        
        results_returned = execute_values(
            cur,
            upsert_query,
            values,
            template="(%s, %s, %s, %s, %s, %s, NOW())",
            page_size=100,
            fetch=True
        )
        
        insert_count = sum(1 for r in results_returned if r[0])
        update_count = sum(1 for r in results_returned if not r[0])
        
        return {'inserted': insert_count, 'updated': update_count}


def update_cache_info(
    conn: Connection,
    url: str,
    cache_path: str,
    file_size: int,
    content_type: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> None:
    """Update cache information for a URL in the database."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE tbl_bolo_link_check
            SET 
                cache_path = %s,
                file_size = %s,
                content_type = COALESCE(%s, content_type),
                metadata = COALESCE(%s, metadata),
                cached_at = NOW(),
                updated_at = NOW()
            WHERE actual_url = %s
        """, (cache_path, file_size, content_type, 
              json.dumps(metadata) if metadata else None, url))


def get_validated_urls(conn: Connection) -> Set[str]:
    """Get set of all URLs that returned HTTP 200."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT actual_url 
            FROM tbl_bolo_link_check 
            WHERE response_code = 200
        """)
        return {row[0] for row in cur.fetchall()}


def get_cached_files_by_uid(conn: Connection) -> Dict[str, List[Dict]]:
    """
    Get all cached files grouped by UID.
    Returns dict: {uid: [{field, actual_url, cache_path, file_size}, ...]}
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT uid, field, actual_url, cache_path, file_size, content_type
            FROM tbl_bolo_link_check
            WHERE cache_path IS NOT NULL
              AND response_code = 200
            ORDER BY uid, field
        """)
        
        results = defaultdict(list)
        for row in cur.fetchall():
            results[row['uid']].append(dict(row))
        
        return dict(results)


def get_link_check_summary(conn: Connection) -> Dict[str, Any]:
    """Get summary statistics from tbl_bolo_link_check."""
    with conn.cursor() as cur:
        # Overall counts by result
        cur.execute("""
            SELECT result, COUNT(*) as count
            FROM tbl_bolo_link_check
            GROUP BY result
            ORDER BY result
        """)
        result_counts = {row[0]: row[1] for row in cur.fetchall()}
        
        # Counts by response code
        cur.execute("""
            SELECT response_code, COUNT(*) as count
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
        
        # Cache statistics
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE cache_path IS NOT NULL) as cached_count,
                COALESCE(SUM(file_size) FILTER (WHERE cache_path IS NOT NULL), 0) as cached_bytes
            FROM tbl_bolo_link_check
        """)
        cache_row = cur.fetchone()
        
        # Unique UIDs
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
            'cache': {
                'files_cached': cache_row[0],
                'total_bytes': cache_row[1],
                'total_mb': round(cache_row[1] / (1024 * 1024), 2) if cache_row[1] else 0
            },
            'last_updated': str(last_updated) if last_updated else None
        }


def get_failed_links(
    conn: Connection,
    limit: int = 100,
    include_timeouts: bool = True
) -> List[Dict[str, Any]]:
    """Get list of failed/timeout links for review."""
    results_filter = "('failure', 'timeout', 'rate_limited')" if include_timeouts else "('failure')"
    
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


# =============================================================================
# MAIN VALIDATION FUNCTION
# =============================================================================

async def validate_links_from_file(file_path: str) -> Dict[str, Any]:
    """
    Main function to validate all links from a JSON data file.
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
    
    # Count Plone URLs (will be marked but not requested)
    plone_count = sum(1 for _, _, url in all_urls if is_plone_url(url))
    
    # Validate URLs asynchronously
    logger.info(f"Starting validation of {len(all_urls)} URLs ({plone_count} Plone URLs will be marked)")
    validation_results = await validate_urls_batch(all_urls)
    
    # Save results to database
    with get_db_connection() as conn:
        db_results = save_validation_results(conn, validation_results)
        conn.commit()
    
    # Calculate summary statistics
    processing_time = (datetime.now() - start_time).total_seconds()
    
    result_counts = defaultdict(int)
    for r in validation_results:
        result_counts[r['result']] += 1
    
    response_codes = defaultdict(int)
    for r in validation_results:
        if r['response_code']:
            response_codes[r['response_code']] += 1
    
    return {
        'status': 'success',
        'total_urls_extracted': len(all_urls),
        'plone_urls_marked': plone_count,
        'urls_validated': len(all_urls) - plone_count,
        'total_records': len(data.get('items', [])),
        'results': dict(result_counts),
        'database': db_results,
        'response_codes': dict(sorted(response_codes.items())),
        'processing_time_seconds': round(processing_time, 2)
    }


# =============================================================================
# ARCHIVE GENERATION
# =============================================================================

def get_person_info(conn: Connection, uid: str) -> Optional[Dict[str, Any]]:
    """Get person details from tbl_bolo for info.txt generation."""
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT 
                uid, title, aliases, dates_of_birth_used, place_of_birth,
                sex, race, hair, eyes, height_min, height_max, 
                weight_min, weight_max, scars_and_marks,
                poster_classification, reward_text, reward_max,
                warning_message, description, caution, remarks,
                status, nationality, url, modified
            FROM tbl_bolo
            WHERE uid = %s AND is_active = TRUE
            ORDER BY modified DESC
            LIMIT 1
        """, (uid,))
        
        row = cur.fetchone()
        return dict(row) if row else None


def format_height(min_inches: Optional[int], max_inches: Optional[int]) -> str:
    """Convert height in inches to feet/inches format."""
    if not min_inches and not max_inches:
        return "Unknown"
    
    def inches_to_str(inches):
        if not inches:
            return None
        feet = inches // 12
        remaining = inches % 12
        return f"{feet}'{remaining}\""
    
    min_str = inches_to_str(min_inches)
    max_str = inches_to_str(max_inches)
    
    if min_str and max_str and min_str != max_str:
        return f"{min_str} - {max_str}"
    return min_str or max_str or "Unknown"


def format_weight(min_lbs: Optional[int], max_lbs: Optional[int]) -> str:
    """Format weight range."""
    if not min_lbs and not max_lbs:
        return "Unknown"
    
    if min_lbs and max_lbs and min_lbs != max_lbs:
        return f"{min_lbs} - {max_lbs} lbs"
    return f"{min_lbs or max_lbs} lbs"


def generate_info_txt(person: Dict[str, Any]) -> str:
    """Generate info.txt content for a person."""
    lines = [
        "=" * 60,
        "FBI WANTED PERSON",
        "=" * 60,
        f"Name: {person.get('title', 'Unknown')}",
        f"UID: {person.get('uid', 'Unknown')}",
        f"Status: {person.get('status', 'Unknown')}",
        ""
    ]
    
    # Aliases
    aliases = person.get('aliases')
    if aliases:
        lines.append(f"Aliases: {', '.join(aliases)}")
    
    # DOB
    dobs = person.get('dates_of_birth_used')
    if dobs:
        lines.append(f"Date(s) of Birth: {', '.join(dobs)}")
    
    # Place of birth
    pob = person.get('place_of_birth')
    if pob:
        lines.append(f"Place of Birth: {pob}")
    
    # Nationality
    nationality = person.get('nationality')
    if nationality:
        lines.append(f"Nationality: {nationality}")
    
    lines.append("")
    lines.append("Physical Description:")
    lines.append(f"  Sex: {person.get('sex', 'Unknown')}")
    lines.append(f"  Race: {person.get('race', 'Unknown')}")
    lines.append(f"  Hair: {person.get('hair', 'Unknown')}")
    lines.append(f"  Eyes: {person.get('eyes', 'Unknown')}")
    lines.append(f"  Height: {format_height(person.get('height_min'), person.get('height_max'))}")
    lines.append(f"  Weight: {format_weight(person.get('weight_min'), person.get('weight_max'))}")
    
    scars = person.get('scars_and_marks')
    if scars:
        lines.append(f"  Scars/Marks: {scars}")
    
    lines.append("")
    
    # Classification and Reward
    classification = person.get('poster_classification')
    if classification:
        lines.append(f"Classification: {classification.replace('_', ' ').title()}")
    
    reward_text = person.get('reward_text')
    reward_max = person.get('reward_max')
    if reward_text:
        lines.append(f"Reward: {reward_text}")
    elif reward_max:
        lines.append(f"Reward: Up to ${reward_max:,}")
    
    lines.append("")
    
    # Warning
    warning = person.get('warning_message')
    if warning:
        lines.append(f"WARNING: {warning}")
        lines.append("")
    
    # Description
    description = person.get('description')
    if description:
        lines.append("Description:")
        # Word wrap at ~70 chars
        words = description.split()
        line = ""
        for word in words:
            if len(line) + len(word) + 1 <= 70:
                line += (" " if line else "") + word
            else:
                lines.append(f"  {line}")
                line = word
        if line:
            lines.append(f"  {line}")
        lines.append("")
    
    # Caution
    caution = person.get('caution')
    if caution:
        lines.append("Caution:")
        lines.append(f"  {caution[:500]}{'...' if len(caution) > 500 else ''}")
        lines.append("")
    
    # Remarks
    remarks = person.get('remarks')
    if remarks:
        lines.append("Remarks:")
        lines.append(f"  {remarks[:500]}{'...' if len(remarks) > 500 else ''}")
        lines.append("")
    
    # FBI URL
    fbi_url = person.get('url')
    if fbi_url:
        lines.append(f"FBI Page: {fbi_url}")
    
    lines.append("")
    lines.append("=" * 60)
    lines.append(f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    lines.append("Source: BoloDoc.com")
    lines.append("=" * 60)
    
    return "\n".join(lines)


def generate_folder_name(person: Dict[str, Any]) -> str:
    """Generate folder name from person data: LASTNAME_FIRSTNAME_uid8."""
    title = person.get('title', 'UNKNOWN')
    uid = person.get('uid', 'unknown')[:8]
    
    # Parse name - typically "LASTNAME, FIRSTNAME MIDDLE" or "FIRSTNAME LASTNAME"
    parts = title.replace(',', ' ').split()
    
    if len(parts) >= 2:
        # Take up to 3 name parts
        name_parts = [sanitize_folder_name(p) for p in parts[:3]]
        name_str = '_'.join(name_parts)
    else:
        name_str = sanitize_folder_name(title)
    
    return f"{name_str}_{uid}"


def generate_manifest(
    generation_time: datetime,
    persons_count: int,
    files_by_type: Dict[str, int],
    total_size: int,
    classifications: Dict[str, int],
    folder_structure: List[Dict[str, Any]]
) -> str:
    """Generate manifest.txt content for the archive root."""
    lines = [
        "=" * 70,
        "FBI BOLO DOCUMENTS ARCHIVE",
        "=" * 70,
        f"Generated: {generation_time.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"Source: BoloDoc.com via FBI Wanted API",
        "",
        "-" * 70,
        "SUMMARY",
        "-" * 70,
        f"Total Persons: {persons_count:,}",
        f"Total Files: {sum(files_by_type.values()):,}",
        f"Total Size: {total_size / (1024*1024):.2f} MB",
        "",
        "-" * 70,
        "FILES BY TYPE",
        "-" * 70,
    ]
    
    for ext, count in sorted(files_by_type.items()):
        lines.append(f"  {ext:12} {count:,} files")
    
    lines.append("")
    lines.append("-" * 70)
    lines.append("PERSONS BY CLASSIFICATION")
    lines.append("-" * 70)
    
    for classification, count in sorted(classifications.items(), key=lambda x: -x[1]):
        lines.append(f"  {classification:25} {count:,}")
    
    lines.append("")
    lines.append("-" * 70)
    lines.append("FOLDER STRUCTURE")
    lines.append("-" * 70)
    
    for folder in folder_structure[:50]:  # Limit to first 50 for readability
        lines.append(f"\n{folder['name']}/")
        for file_name in folder.get('files', [])[:5]:  # Limit files shown
            lines.append(f"    {file_name}")
        if len(folder.get('files', [])) > 5:
            lines.append(f"    ... and {len(folder['files']) - 5} more files")
    
    if len(folder_structure) > 50:
        lines.append(f"\n... and {len(folder_structure) - 50} more folders")
    
    lines.append("")
    lines.append("=" * 70)
    lines.append("END OF MANIFEST")
    lines.append("=" * 70)
    
    return "\n".join(lines)


async def download_files_for_archive(conn: Connection) -> Dict[str, Any]:
    """
    Download all validated files to cache.
    Uses existing cache when available.
    """
    start_time = datetime.now()
    
    # Get all URLs that need files
    with conn.cursor() as cur:
        cur.execute("""
            SELECT uid, field, actual_url, cache_path
            FROM tbl_bolo_link_check
            WHERE response_code = 200
              AND result = 'success'
        """)
        urls_to_process = cur.fetchall()
    
    if not urls_to_process:
        return {
            "status": "no_files",
            "message": "No validated URLs to download"
        }
    
    # Get set of already validated URLs
    validated_urls = get_validated_urls(conn)
    
    # Track statistics
    from_cache = 0
    downloaded = 0
    failed = 0
    total_bytes = 0
    
    ensure_cache_dir()
    
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True
    ) as client:
        
        for uid, field, url, existing_cache_path in urls_to_process:
            result = await download_file_with_cache(client, url, validated_urls)
            
            if result['success']:
                if result['from_cache']:
                    from_cache += 1
                else:
                    downloaded += 1
                
                total_bytes += result['file_size']
                
                # Update database with cache info
                if result['cache_path'] and not existing_cache_path:
                    update_cache_info(
                        conn, url,
                        result['cache_path'],
                        result['file_size'],
                        result.get('content_type')
                    )
            else:
                failed += 1
            
            # Small delay between downloads
            if not result['from_cache']:
                await asyncio.sleep(REQUEST_DELAY)
        
        conn.commit()
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    return {
        "status": "success",
        "files_from_cache": from_cache,
        "files_downloaded": downloaded,
        "files_failed": failed,
        "total_files": from_cache + downloaded,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "processing_time_seconds": round(processing_time, 2),
        "processing_time_minutes": round(processing_time / 60, 2)
    }


def create_documents_archive() -> Dict[str, Any]:
    """
    Create the ZIP archive with per-person folders.
    """
    start_time = datetime.now()
    generation_time = datetime.utcnow()
    
    ensure_cache_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    with get_db_connection() as conn:
        # Get cached files grouped by UID
        files_by_uid = get_cached_files_by_uid(conn)
        
        if not files_by_uid:
            return {
                "status": "error",
                "message": "No cached files available. Run download_files first."
            }
        
        # Track statistics
        persons_count = 0
        files_by_type = defaultdict(int)
        total_size = 0
        classifications = defaultdict(int)
        folder_structure = []
        
        # Create ZIP file
        with zipfile.ZipFile(ARCHIVE_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
            
            for uid, files in files_by_uid.items():
                # Get person info
                person = get_person_info(conn, uid)
                if not person:
                    continue
                
                persons_count += 1
                
                # Track classification
                classification = person.get('poster_classification', 'other') or 'other'
                classifications[classification] += 1
                
                # Generate folder name
                folder_name = generate_folder_name(person)
                folder_files = []
                
                # Generate and add info.txt
                info_content = generate_info_txt(person)
                info_path = f"{folder_name}/info.txt"
                zf.writestr(info_path, info_content.encode('utf-8'))
                files_by_type['.txt'] += 1
                total_size += len(info_content.encode('utf-8'))
                folder_files.append('info.txt')
                
                # Add cached files
                for file_info in files:
                    cache_path = DATA_DIR / file_info['cache_path']
                    
                    if not cache_path.exists():
                        continue
                    
                    # Determine filename in archive
                    ext = cache_path.suffix.lower()
                    field = file_info['field']
                    
                    # Create meaningful filename
                    if 'files_' in field:
                        base_name = f"document_{field.split('_')[1]}"
                    elif 'images_' in field:
                        idx = field.split('_')[1]
                        img_type = field.split('_')[2] if len(field.split('_')) > 2 else 'image'
                        base_name = f"{img_type}_{idx}"
                    else:
                        base_name = field
                    
                    archive_filename = f"{base_name}{ext}"
                    archive_path = f"{folder_name}/{archive_filename}"
                    
                    # Add to ZIP
                    zf.write(cache_path, archive_path)
                    
                    file_size = file_info.get('file_size', 0)
                    files_by_type[ext] += 1
                    total_size += file_size
                    folder_files.append(archive_filename)
                
                folder_structure.append({
                    'name': folder_name,
                    'files': folder_files
                })
            
            # Generate and add manifest
            manifest_content = generate_manifest(
                generation_time,
                persons_count,
                dict(files_by_type),
                total_size,
                dict(classifications),
                folder_structure
            )
            zf.writestr('manifest.txt', manifest_content.encode('utf-8'))
    
    processing_time = (datetime.now() - start_time).total_seconds()
    archive_size = ARCHIVE_PATH.stat().st_size
    
    return {
        "status": "success",
        "archive_path": str(ARCHIVE_PATH),
        "archive_size_bytes": archive_size,
        "archive_size_mb": round(archive_size / (1024 * 1024), 2),
        "persons_count": persons_count,
        "total_files": sum(files_by_type.values()),
        "files_by_type": dict(files_by_type),
        "classifications": dict(classifications),
        "generation_time": generation_time.isoformat(),
        "processing_time_seconds": round(processing_time, 2)
    }


def get_archive_info() -> Optional[Dict[str, Any]]:
    """Get information about the current archive file."""
    if not ARCHIVE_PATH.exists():
        return None
    
    stat = ARCHIVE_PATH.stat()
    
    return {
        "exists": True,
        "path": str(ARCHIVE_PATH),
        "size_bytes": stat.st_size,
        "size_mb": round(stat.st_size / (1024 * 1024), 2),
        "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
    }


def get_archive_file_path() -> Optional[Path]:
    """Get path to archive file if it exists."""
    if ARCHIVE_PATH.exists():
        return ARCHIVE_PATH
    return None
