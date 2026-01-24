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
import warnings
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


def should_skip_url(url: str) -> bool:
    """
    Skip API endpoints, Plone routing, AND:
    - URLs without valid file extensions
    - URLs with redirect parameters
    
    NOTE: We do NOT skip @@download URLs anymore - these contain valid PDFs
    in multiple languages that should be downloaded by deriving the base URL.
    """
    # 1. Pattern-based skipping (removed @@download and /@@)
    skip_patterns = [
        '/@wanted-person/',
        '/@',
        '/acl_users/',
        '/require_login',
    ]
    
    url_lower = url.lower()
    for pattern in skip_patterns:
        if pattern.lower() in url_lower:
            return True
    
    # 2. Check for redirect parameters (NEW)
    redirect_params = [
        'came_from=http',
        'came_from=https',
        'came_from=http%3a',   # URL-encoded
        'came_from=https%3a',
        'redirect_url=',
        'return_to=http',
        'return_to=https',
        'next=http',
        'next=https',
    ]
    
    for param in redirect_params:
        if param in url_lower:
            return True
    
    # 3. Check file extension (NEW)
    url_path = url.split('?')[0].split('#')[0]  # Remove query/fragment
    
    if '.' in url_path:
        ext = url_path.rsplit('.', 1)[-1].lower()
        
        # Valid extensions we want to download
        valid_extensions = {
            'pdf', 'txt', 'log',   # Documents
            'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'svg',  # Images
        }
        
        if ext in valid_extensions:
            return False  # Keep it
    
    # No valid extension - skip it
    return True


def get_valid_file_extensions() -> set:
    """
    Return set of valid file extensions for download.
    Used by should_skip_url() to determine downloadable content.
    """
    return {
        # Documents
        'pdf', 'txt', 'log', 
        # Images
        'jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'tiff', 'tif', 'svg',
    }


def derive_base_url_from_download(url: str) -> Optional[str]:
    """
    Derive the base URL from a Plone @@download URL.
    
    Plone uses URLs like:
    https://www.fbi.gov/path/to/file.pdf/@@download/file/FileName.pdf
    
    The actual downloadable URL (without Plone issues) is:
    https://www.fbi.gov/path/to/file.pdf
    
    Args:
        url: Full URL potentially containing @@download
        
    Returns:
        Base URL (everything before /@@download) if pattern matches, None otherwise
        
    Examples:
        >>> derive_base_url_from_download('https://fbi.gov/doc.pdf/@@download/file/Doc.pdf')
        'https://fbi.gov/doc.pdf'
        >>> derive_base_url_from_download('https://fbi.gov/doc.pdf')
        None
    """
    if '@@download' not in url.lower():
        return None
    
    # Find position of @@download (case-insensitive)
    idx = url.lower().find('/@@download')
    if idx == -1:
        return None
    
    # Extract base URL (everything before /@@download)
    base_url = url[:idx]
    
    # Validate it's a proper URL with a file extension
    if is_valid_url(base_url) and get_file_extension(base_url):
        return base_url
    
    return None


def has_redirect_in_query(url: str) -> bool:
    """
    Check if URL has authentication/redirect parameters in query string.
    These typically return 403 Forbidden when accessed by bots.
    
    Examples:
    - https://www.fbi.gov/login?came_from=https%3A%2F%2Fwww.fbi.gov%2Fwanted
    - https://example.com/path?redirect_url=http://...
    - https://example.com/page?return_to=https://...
    
    Returns:
        True if URL has redirect parameters, False otherwise
    """
    url_lower = url.lower()
    
    redirect_params = [
        'came_from=http',
        'came_from=https',
        'came_from=http%3a',   # URL-encoded
        'came_from=https%3a',
        'redirect_url=',
        'return_to=http',
        'return_to=https',
        'next=http',
        'next=https',
    ]
    
    return any(param in url_lower for param in redirect_params)


def get_file_extension(url: str) -> str:
    """
    Extract file extension from URL.
    Removes query string and fragment before extracting extension.
    
    Args:
        url: Full URL
        
    Returns:
        File extension without dot (e.g., 'pdf', 'jpg'), or empty string if none
    """
    # Remove query string and fragment
    url_path = url.split('?')[0].split('#')[0]
    
    # Get extension
    if '.' in url_path:
        return url_path.rsplit('.', 1)[-1].lower()
    
    return ''


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


def calculate_content_hash(record: dict) -> str:
    """
    Generate SHA256 hash from actual content fields only.
    
    Excludes timestamps and server-generated metadata that changes
    on every page load but doesn't represent real content changes.
    
    This solves the problem where web-scraped records show as "modified"
    on every run because the server timestamp updates, even when
    actual content hasn't changed.
    
    Args:
        record: Full record dictionary (from API or web scrape)
        
    Returns:
        SHA256 hex digest of content (64 character string)
    """
    # Extract only substantive content fields
    content_fields = {
        'title': record.get('title', ''),
        'description': record.get('description', ''),
        'subjects': sorted(record.get('subjects', []) if record.get('subjects') else []),
        'warning_message': record.get('warning_message', ''),
        'reward_text': record.get('reward_text', ''),
        'caution': record.get('caution', ''),
        'details': record.get('details', ''),
        'remarks': record.get('remarks', ''),
        'field_offices': sorted(record.get('field_offices', []) if record.get('field_offices') else []),
        'person_classification': record.get('person_classification', ''),
        'status': record.get('status', ''),
        'age_range': record.get('age_range', ''),
        'sex': record.get('sex', ''),
        'race': record.get('race', ''),
        'nationality': record.get('nationality', ''),
        'hair': record.get('hair', ''),
        'eyes': record.get('eyes', ''),
        'height_min': record.get('height_min'),
        'height_max': record.get('height_max'),
        'weight_min': record.get('weight_min'),
        'weight_max': record.get('weight_max'),
        'build': record.get('build', ''),
        'complexion': record.get('complexion', ''),
        'scars_and_marks': record.get('scars_and_marks', ''),
        'occupations': sorted(record.get('occupations', []) if record.get('occupations') else []),
        'languages': sorted(record.get('languages', []) if record.get('languages') else []),
        # File and image URLs (not timestamps, just URLs)
        'images': sorted([
            img.get('original', '') or img.get('large', '') or img.get('thumb', '')
            for img in record.get('images', []) if img
        ]),
        'files': sorted([
            f.get('url', '')
            for f in record.get('files', []) if f
        ]),
    }
    
    # Create stable JSON representation (sorted keys, consistent format)
    content_json = json.dumps(content_fields, sort_keys=True, default=str)
    
    # Generate and return hash
    return hashlib.sha256(content_json.encode('utf-8')).hexdigest()


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
    
    For @@download URLs, also extracts the derived base URL which is
    the direct download link without Plone routing issues.
    
    Returns:
        List of tuples: (uid, field_name, url)
    """
    urls = []
    uid = item.get('uid')
    
    if not uid:
        return urls
    
    # 1. pathId - direct URL field
    path_id = item.get('pathId')
    if is_valid_url(path_id) and not should_skip_url(path_id):
        urls.append((uid, 'path_id', path_id))
        # Check for @@download and derive base URL
        base_url = derive_base_url_from_download(path_id)
        if base_url:
            urls.append((uid, 'path_id_derived', base_url))
    
    # 2. url - direct URL field
    url = item.get('url')
    if is_valid_url(url) and not should_skip_url(url):
        urls.append((uid, 'url', url))
        # Check for @@download and derive base URL
        base_url = derive_base_url_from_download(url)
        if base_url:
            urls.append((uid, 'url_derived', base_url))

    # 3. files[].url - array of file objects
    files = item.get('files') or []
    for idx, file_obj in enumerate(files):
        if isinstance(file_obj, dict):
            file_url = file_obj.get('url')
            if is_valid_url(file_url):
                urls.append((uid, f'files_{idx}_url', file_url))
                # Check for @@download and derive base URL
                base_url = derive_base_url_from_download(file_url)
                if base_url:
                    urls.append((uid, f'files_{idx}_url_derived', base_url))
    
    # 4. images[] - array of image objects with large, thumb, original
    images = item.get('images') or []
    for idx, image_obj in enumerate(images):
        if isinstance(image_obj, dict):
            # large
            large_url = image_obj.get('large')
            if is_valid_url(large_url):
                urls.append((uid, f'images_{idx}_large', large_url))
                base_url = derive_base_url_from_download(large_url)
                if base_url:
                    urls.append((uid, f'images_{idx}_large_derived', base_url))
            
            # thumb
            thumb_url = image_obj.get('thumb')
            if is_valid_url(thumb_url):
                urls.append((uid, f'images_{idx}_thumb', thumb_url))
                base_url = derive_base_url_from_download(thumb_url)
                if base_url:
                    urls.append((uid, f'images_{idx}_thumb_derived', base_url))
            
            # original
            original_url = image_obj.get('original')
            if is_valid_url(original_url):
                urls.append((uid, f'images_{idx}_original', original_url))
                base_url = derive_base_url_from_download(original_url)
                if base_url:
                    urls.append((uid, f'images_{idx}_original_derived', base_url))
    
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


def extract_urls_from_record_web(item: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Extract all URLs from a single web-scraped BOLO record.
    Includes support for related_cases which is unique to web data.
    
    For @@download URLs, also extracts the derived base URL which is
    the direct download link without Plone routing issues.
    
    Returns:
        List of tuples: (uid, field_name, url)
    """
    urls = []
    uid = item.get('uid')
    
    if not uid:
        return urls
    
    # 1. pathId - direct URL field
    path_id = item.get('pathId')
    if is_valid_url(path_id) and not should_skip_url(path_id):
        urls.append((uid, 'path_id', path_id))
        # Check for @@download and derive base URL
        base_url = derive_base_url_from_download(path_id)
        if base_url:
            urls.append((uid, 'path_id_derived', base_url))
    
    # 2. url - direct URL field
    url = item.get('url')
    if is_valid_url(url) and not should_skip_url(url):
        urls.append((uid, 'url', url))
        # Check for @@download and derive base URL
        base_url = derive_base_url_from_download(url)
        if base_url:
            urls.append((uid, 'url_derived', base_url))
    
    # 3. files[].url - array of file objects
    files = item.get('files') or []
    for idx, file_obj in enumerate(files):
        if isinstance(file_obj, dict):
            file_url = file_obj.get('url')
            if is_valid_url(file_url) and not should_skip_url(file_url):
                urls.append((uid, f'files_{idx}_url', file_url))
                # Check for @@download and derive base URL
                base_url = derive_base_url_from_download(file_url)
                if base_url:
                    urls.append((uid, f'files_{idx}_url_derived', base_url))
    
    # 4. images[] - array of image objects with large, thumb, original
    images = item.get('images') or []
    for idx, image_obj in enumerate(images):
        if isinstance(image_obj, dict):
            # large
            large_url = image_obj.get('large')
            if is_valid_url(large_url) and not should_skip_url(large_url):
                urls.append((uid, f'images_{idx}_large', large_url))
                base_url = derive_base_url_from_download(large_url)
                if base_url:
                    urls.append((uid, f'images_{idx}_large_derived', base_url))
            
            # thumb
            thumb_url = image_obj.get('thumb')
            if is_valid_url(thumb_url) and not should_skip_url(thumb_url):
                urls.append((uid, f'images_{idx}_thumb', thumb_url))
                base_url = derive_base_url_from_download(thumb_url)
                if base_url:
                    urls.append((uid, f'images_{idx}_thumb_derived', base_url))
            
            # original
            original_url = image_obj.get('original')
            if is_valid_url(original_url) and not should_skip_url(original_url):
                urls.append((uid, f'images_{idx}_original', original_url))
                base_url = derive_base_url_from_download(original_url)
                if base_url:
                    urls.append((uid, f'images_{idx}_original_derived', base_url))
    
    # 5. related_cases[] - unique to web data
    related_cases = item.get('related_cases') or []
    for idx, case_url in enumerate(related_cases):
        if is_valid_url(case_url) and not should_skip_url(case_url):
            urls.append((uid, f'related_cases_{idx}', case_url))
            # Check for @@download and derive base URL
            base_url = derive_base_url_from_download(case_url)
            if base_url:
                urls.append((uid, f'related_cases_{idx}_derived', base_url))
    
    return urls


def extract_all_urls_from_data_web(data: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """
    Extract all URLs from web-scraped FBI data.
    
    Returns:
        List of tuples: (uid, field_name, url)
    """
    all_urls = []
    items = data.get('items', [])
    
    for item in items:
        urls = extract_urls_from_record_web(item)
        all_urls.extend(urls)
    
    logger.info(f"Extracted {len(all_urls)} URLs from {len(items)} web records")
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


def save_validation_results_web(conn: Connection, results: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Save web validation results to tbl_bolo_link_check_web using UPSERT.
    Maps API validation result format to web table schema.
    """
    if not results:
        return {'inserted': 0, 'updated': 0}
    
    values = []
    for r in results:
        # Map field names to url_type
        # Extract file_name if this is a files_ field
        field = r['field']
        file_name = None
        
        if field.startswith('files_'):
            url_type = 'file'
            # Try to extract filename from URL
            url_parts = r['actual_url'].split('/')
            if url_parts:
                file_name = url_parts[-1]
        elif field.startswith('images_'):
            url_type = 'poster'
        elif field.startswith('related_cases_'):
            url_type = 'related_case'
        elif field == 'url':
            url_type = 'profile'
        else:
            url_type = field
        
        # Map result to is_valid
        is_valid = (r['result'] == 'success')
        
        values.append((
            r['uid'],
            r['actual_url'],
            url_type,
            file_name,
            r['response_code'],
            is_valid,
            r.get('content_type'),
            None  # error_message - we'll use result if not success
        ))
    
    with conn.cursor() as cur:
        upsert_query = """
            INSERT INTO tbl_bolo_link_check_web (
                uid, url, url_type, file_name, http_status, is_valid, 
                content_type, error_message, check_timestamp
            )
            VALUES %s
            ON CONFLICT (uid, url, url_type, COALESCE(file_name, ''))
            DO UPDATE SET
                http_status = EXCLUDED.http_status,
                is_valid = EXCLUDED.is_valid,
                content_type = EXCLUDED.content_type,
                error_message = EXCLUDED.error_message,
                check_timestamp = NOW()
            RETURNING (xmax = 0) as is_insert
        """
        
        results_returned = execute_values(
            cur,
            upsert_query,
            values,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, NOW())",
            page_size=100,
            fetch=True
        )
        
        insert_count = sum(1 for r in results_returned if r[0])
        update_count = sum(1 for r in results_returned if not r[0])
        
        return {'inserted': insert_count, 'updated': update_count}


def update_cache_info_web(
    conn: Connection,
    url: str,
    cache_path: str,
    file_size: int,
    content_type: Optional[str] = None
) -> None:
    """Update cache information for a web URL in the database."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE tbl_bolo_link_check_web
            SET 
                content_length = %s,
                content_type = COALESCE(%s, content_type),
                check_timestamp = NOW()
            WHERE url = %s
        """, (file_size, content_type, url))


def get_validated_urls_web(conn: Connection) -> Set[str]:
    """Get set of all web URLs that returned HTTP 200."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT url 
            FROM tbl_bolo_link_check_web 
            WHERE http_status = 200
        """)
        return {row[0] for row in cur.fetchall()}


def get_cached_files_by_uid(conn: Connection) -> Dict[str, List[Dict]]:
    """
    Get all cached files grouped by UID from BOTH API and web sources.
    Returns dict: {uid: [{field, actual_url, cache_path, file_size, source}, ...]}
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Get files from API data
        cur.execute("""
            SELECT uid, field, actual_url, cache_path, file_size, content_type, 'api' as source
            FROM tbl_bolo_link_check
            WHERE cache_path IS NOT NULL
              AND response_code = 200
            ORDER BY uid, field
        """)
        
        results = defaultdict(list)
        for row in cur.fetchall():
            row_dict = dict(row)
            results[row_dict['uid']].append(row_dict)
        
        # Get files from web data
        # Note: tbl_bolo_link_check_web doesn't have cache_path column yet
        # We'll need to map url to cache using the same hashing logic
        cur.execute("""
            SELECT uid, url_type as field, url as actual_url, content_length as file_size, 
                   content_type, 'web' as source
            FROM tbl_bolo_link_check_web
            WHERE http_status = 200
              AND is_valid = TRUE
            ORDER BY uid, url_type
        """)
        
        for row in cur.fetchall():
            row_dict = dict(row)
            # Generate cache path using same logic as API files
            cache_filename = get_cache_filename(row_dict['actual_url'])
            cache_path = CACHE_DIR / cache_filename
            if cache_path.exists():
                row_dict['cache_path'] = str(cache_path.relative_to(DATA_DIR))
            results[row_dict['uid']].append(row_dict)
        
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
    
    items = data.get('items', [])
    logger.info(f"Loaded {len(items)} records from {file_path}")
    
    # Extract all URLs (filtering happens inside extract_urls_from_record)
    # URLs with @, @@, /acl_users/, etc. are automatically skipped
    all_urls = extract_all_urls_from_data(data)
    
    if not all_urls:
        logger.warning("No valid URLs found after extraction and filtering")
        return {
            'status': 'success',
            'message': 'No URLs found to validate (all filtered or none present)',
            'total_urls': 0,
            'total_records': len(items),
            'processing_time_seconds': 0
        }
    
    # Count Plone URLs (will be marked as plone_url=true but not validated)
    # These return 403 from automated requests but work in browsers
    plone_count = sum(1 for _, _, url in all_urls if is_plone_url(url))
    
    # Calculate actual validation count
    urls_to_validate = len(all_urls) - plone_count
    
    # Log validation plan
    logger.info(f"Extracted {len(all_urls)} URLs from {len(items)} records")
    logger.info(f"  - {plone_count} Plone URLs (will be marked but not validated)")
    logger.info(f"  - {urls_to_validate} URLs will be validated")
    logger.info("Note: URLs with @, @@, /acl_users/ were filtered during extraction")
    
    # Validate URLs asynchronously
    logger.info(f"Starting validation of {len(all_urls)} URLs ({plone_count} Plone URLs will be marked)")
    validation_results = await validate_urls_batch(all_urls)
    
    # Save results to database
    logger.info(f"Saving {len(validation_results)} validation results to database")
    with get_db_connection() as conn:
        db_results = save_validation_results(conn, validation_results)
        conn.commit()
    
    # Calculate summary statistics
    processing_time = (datetime.now() - start_time).total_seconds()
    
    # Count results by type
    result_counts = defaultdict(int)
    for r in validation_results:
        result_counts[r['result']] += 1
    
    # Count response codes
    response_codes = defaultdict(int)
    for r in validation_results:
        if r['response_code']:
            response_codes[r['response_code']] += 1
    
    # Log summary
    logger.info(f"Validation complete in {processing_time:.2f}s")
    logger.info(f"Results: {dict(result_counts)}")
    
    return {
        'status': 'success',
        'total_urls_extracted': len(all_urls),
        'plone_urls_marked': plone_count,
        'urls_validated': urls_to_validate,
        'total_records': len(items),
        'results': dict(result_counts),
        'database': db_results,
        'response_codes': dict(sorted(response_codes.items())),
        'processing_time_seconds': round(processing_time, 2),
        'notes': {
            'filtered_patterns': 'URLs with @, @@, /acl_users/, /require_login filtered at extraction',
            'plone_handling': 'Plone URLs marked but not validated (return 403 for bots)'
        }
    }


async def validate_links_from_file_web(file_path: str) -> Dict[str, Any]:
    """
    Validate all links from a web-scraped JSON data file.
    Saves results to tbl_bolo_link_check_web instead of tbl_bolo_link_check.
    """
    start_time = datetime.now()
    
    # Load JSON data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Error loading web JSON file: {str(e)}")
        raise
    
    items = data.get('items', [])
    logger.info(f"Loaded {len(items)} web-scraped records from {file_path}")
    
    # Extract all URLs using web-specific extractor
    # Filtering happens inside extract_urls_from_record_web()
    # URLs with @, @@, /acl_users/, etc. are automatically skipped
    all_urls = extract_all_urls_from_data_web(data)
    
    if not all_urls:
        logger.warning("No valid URLs found in web data after extraction and filtering")
        return {
            'status': 'success',
            'message': 'No URLs found to validate in web data (all filtered or none present)',
            'total_urls': 0,
            'total_records': len(items),
            'processing_time_seconds': 0
        }
    
    # Count Plone URLs (will be marked as plone_url=true but not validated)
    # These return 403 from automated requests but work in browsers
    plone_count = sum(1 for _, _, url in all_urls if is_plone_url(url))
    
    # Calculate actual validation count
    urls_to_validate = len(all_urls) - plone_count
    
    # Log validation plan
    logger.info(f"Extracted {len(all_urls)} URLs from {len(items)} web records")
    logger.info(f"  - {plone_count} Plone URLs (will be marked but not validated)")
    logger.info(f"  - {urls_to_validate} URLs will be validated")
    logger.info("Note: URLs with @, @@, /acl_users/ were filtered during extraction")
    logger.info("Web data includes related_cases[] which may have additional URLs")
    
    # Validate URLs asynchronously
    logger.info(f"Starting web validation of {len(all_urls)} URLs ({plone_count} Plone URLs will be marked)")
    validation_results = await validate_urls_batch(all_urls)
    
    # Save results to web-specific table
    logger.info(f"Saving {len(validation_results)} validation results to tbl_bolo_link_check_web")
    with get_db_connection() as conn:
        db_results = save_validation_results_web(conn, validation_results)
        conn.commit()
    
    # Calculate summary statistics
    processing_time = (datetime.now() - start_time).total_seconds()
    
    # Count results by type
    result_counts = defaultdict(int)
    for r in validation_results:
        result_counts[r['result']] += 1
    
    # Count response codes
    response_codes = defaultdict(int)
    for r in validation_results:
        if r['response_code']:
            response_codes[r['response_code']] += 1
    
    # Log summary
    logger.info(f"Web validation complete in {processing_time:.2f}s")
    logger.info(f"Results: {dict(result_counts)}")
    
    return {
        'status': 'success',
        'total_urls_extracted': len(all_urls),
        'plone_urls_marked': plone_count,
        'urls_validated': urls_to_validate,
        'total_records': len(items),
        'results': dict(result_counts),
        'database': db_results,
        'response_codes': dict(sorted(response_codes.items())),
        'processing_time_seconds': round(processing_time, 2),
        'notes': {
            'filtered_patterns': 'URLs with @, @@, /acl_users/, /require_login filtered at extraction',
            'plone_handling': 'Plone URLs marked but not validated (return 403 for bots)',
            'web_specific': 'Includes related_cases[] unique to web scraping'
        }
    }


# =============================================================================
# ARCHIVE GENERATION
# =============================================================================

def get_person_info(conn: Connection, uid: str) -> Optional[Dict[str, Any]]:
    """
    Get person details for info.txt generation.
    Checks both tbl_bolo_web and tbl_bolo, preferring web data if available.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Try web data first (most recent scrape, more complete)
        cur.execute("""
            SELECT 
                uid, title, aliases, dates_of_birth_used, place_of_birth,
                sex, race, hair, eyes, height_min, height_max, 
                weight_min, weight_max, scars_and_marks,
                poster_classification, reward_text, reward_max,
                warning_message, description, caution, remarks,
                status, nationality, url, modified, 'web' as data_source
            FROM tbl_bolo_web
            WHERE uid = %s AND is_active = TRUE
            ORDER BY modified DESC
            LIMIT 1
        """, (uid,))
        
        row = cur.fetchone()
        if row:
            return dict(row)
        
        # Fallback to API data if web data not available
        cur.execute("""
            SELECT 
                uid, title, aliases, dates_of_birth_used, place_of_birth,
                sex, race, hair, eyes, height_min, height_max, 
                weight_min, weight_max, scars_and_marks,
                poster_classification, reward_text, reward_max,
                warning_message, description, caution, remarks,
                status, nationality, url, modified, 'api' as data_source
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
    data_source = person.get('data_source', 'unknown').upper()
    
    lines = [
        "=" * 60,
        "FBI WANTED PERSON",
        "=" * 60,
        f"Name: {person.get('title', 'Unknown')}",
        f"UID: {person.get('uid', 'Unknown')}",
        f"Status: {person.get('status', 'Unknown')}",
        f"Data Source: {data_source}",
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
    folder_structure: List[Dict[str, Any]],
    api_count: int = 0,
    web_count: int = 0
) -> str:
    """Generate manifest.txt content for the archive root."""
    lines = [
        "=" * 70,
        "FBI BOLO DOCUMENTS ARCHIVE",
        "=" * 70,
        f"Generated: {generation_time.strftime('%Y-%m-%d %H:%M:%S')} UTC",
        f"Source: BoloDoc.io via FBI API and Web Scraping",
        "",
        "-" * 70,
        "SUMMARY",
        "-" * 70,
        f"Total Persons: {persons_count:,}",
        f"Total Files: {sum(files_by_type.values()):,}",
        f"Total Size: {total_size / (1024*1024):.2f} MB",
        "",
        "Data Sources:",
        f"  API Data: {api_count:,} files",
        f"  Web Data: {web_count:,} files",
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
    Download all validated files to cache from BOTH API and web sources.
    Uses existing cache when available.
    """
    start_time = datetime.now()
    
    # Get all URLs that need files from API table
    with conn.cursor() as cur:
        cur.execute("""
            SELECT uid, field, actual_url, cache_path, 'api' as source
            FROM tbl_bolo_link_check
            WHERE response_code = 200
              AND result = 'success'
        """)
        api_urls = cur.fetchall()
        
        # Get all URLs that need files from web table
        cur.execute("""
            SELECT uid, url_type as field, url as actual_url, 'web' as source
            FROM tbl_bolo_link_check_web
            WHERE http_status = 200
              AND is_valid = TRUE
        """)
        web_urls = cur.fetchall()
    
    # Combine both sources
    all_urls = list(api_urls) + list(web_urls)
    total_urls = len(all_urls)
    
    if not all_urls:
        return {
            "status": "no_files",
            "message": "No validated URLs to download from either source"
        }
    
    logger.info(f"Starting file download: {total_urls} URLs to process (API: {len(api_urls)}, Web: {len(web_urls)})")
    
    # Get sets of validated URLs from both sources
    validated_urls_api = get_validated_urls(conn)
    validated_urls_web = get_validated_urls_web(conn)
    validated_urls = validated_urls_api | validated_urls_web
    
    # Track statistics
    from_cache = 0
    downloaded = 0
    failed = 0
    total_bytes = 0
    api_count = 0
    web_count = 0
    processed = 0
    
    # Progress logging settings
    log_interval = max(50, total_urls // 20)  # Log every 50 files or 5% of total
    
    ensure_cache_dir()
    
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True
    ) as client:
        
        for row in all_urls:
            uid = row[0]
            field = row[1]
            url = row[2]
            source = row[3] if len(row) > 3 else 'api'
            existing_cache_path = row[3] if source == 'api' and len(row) > 4 else None
            
            result = await download_file_with_cache(client, url, validated_urls)
            
            if result['success']:
                if result['from_cache']:
                    from_cache += 1
                else:
                    downloaded += 1
                
                total_bytes += result['file_size']
                
                # Track by source
                if source == 'api':
                    api_count += 1
                else:
                    web_count += 1
                
                # Update database with cache info
                if result['cache_path']:
                    if source == 'api' and not existing_cache_path:
                        update_cache_info(
                            conn, url,
                            result['cache_path'],
                            result['file_size'],
                            result.get('content_type')
                        )
                    elif source == 'web':
                        update_cache_info_web(
                            conn, url,
                            result['cache_path'],
                            result['file_size'],
                            result.get('content_type')
                        )
            else:
                failed += 1
            
            # Progress logging
            processed += 1
            if processed % log_interval == 0 or processed == total_urls:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = processed / elapsed if elapsed > 0 else 0
                remaining = total_urls - processed
                eta_seconds = remaining / rate if rate > 0 else 0
                eta_minutes = eta_seconds / 60
                
                logger.info(
                    f"Download progress: {processed}/{total_urls} files "
                    f"({100*processed/total_urls:.1f}%), "
                    f"cache: {from_cache}, new: {downloaded}, failed: {failed}, "
                    f"ETA: {eta_minutes:.1f} min"
                )
            
            # Small delay between downloads
            if not result['from_cache']:
                await asyncio.sleep(REQUEST_DELAY)
        
        conn.commit()
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    # Final summary log
    logger.info(
        f"Download complete: {from_cache + downloaded} files in {processing_time:.1f}s "
        f"(cache: {from_cache}, new: {downloaded}, failed: {failed}, "
        f"API: {api_count}, Web: {web_count}, {total_bytes / (1024*1024):.1f} MB)"
    )
    
    return {
        "status": "success",
        "files_from_cache": from_cache,
        "files_downloaded": downloaded,
        "files_failed": failed,
        "total_files": from_cache + downloaded,
        "api_files": api_count,
        "web_files": web_count,
        "total_bytes": total_bytes,
        "total_mb": round(total_bytes / (1024 * 1024), 2),
        "processing_time_seconds": round(processing_time, 2),
        "processing_time_minutes": round(processing_time / 60, 2)
    }


def create_documents_archive() -> Dict[str, Any]:
    """
    Create the ZIP archive with per-person folders.
    Includes files from both API and web sources.
    """
    start_time = datetime.now()
    generation_time = datetime.utcnow()
    
    ensure_cache_dir()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting archive creation...")
    
    with get_db_connection() as conn:
        # Get cached files grouped by UID (from both sources)
        files_by_uid = get_cached_files_by_uid(conn)
        
        if not files_by_uid:
            return {
                "status": "error",
                "message": "No cached files available. Run download_files first."
            }
        
        logger.info(f"Found {len(files_by_uid)} persons with cached files")
        
        # Track statistics
        persons_count = 0
        files_by_type = defaultdict(int)
        total_size = 0
        classifications = defaultdict(int)
        folder_structure = []
        api_file_count = 0
        web_file_count = 0
        duplicates_skipped = 0
        files_not_found = 0
        
        # Create ZIP file (suppress duplicate warnings - we handle them ourselves)
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='Duplicate name:', category=UserWarning)
            with zipfile.ZipFile(ARCHIVE_PATH, 'w', zipfile.ZIP_DEFLATED) as zf:
                # Track all archive paths to prevent duplicates
                added_paths = set()
                
                for uid, files in files_by_uid.items():
                    # Get person info (from web or api)
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
                    if info_path not in added_paths:
                        zf.writestr(info_path, info_content.encode('utf-8'))
                        added_paths.add(info_path)
                        files_by_type['.txt'] += 1
                        total_size += len(info_content.encode('utf-8'))
                        folder_files.append('info.txt')
                    
                    # Add cached files
                    for file_info in files:
                        # Track source
                        source = file_info.get('source', 'api')
                        
                        # Get cache path
                        if 'cache_path' in file_info and file_info['cache_path']:
                            cache_path = DATA_DIR / file_info['cache_path']
                        else:
                            # For web files without cache_path, construct it
                            cache_filename = get_cache_filename(file_info['actual_url'])
                            cache_path = CACHE_DIR / cache_filename
                        
                        if not cache_path.exists():
                            files_not_found += 1
                            continue
                        
                        # Determine filename in archive
                        ext = cache_path.suffix.lower()
                        field = file_info['field']
                        
                        # Create meaningful filename
                        if 'files_' in field or field == 'file':
                            if 'files_' in field:
                                base_name = f"document_{field.split('_')[1]}"
                            else:
                                base_name = "document"
                        elif 'images_' in field or field == 'poster':
                            if 'images_' in field:
                                idx = field.split('_')[1]
                                img_type = field.split('_')[2] if len(field.split('_')) > 2 else 'image'
                                base_name = f"{img_type}_{idx}"
                            else:
                                base_name = "poster"
                        elif 'related_case' in field:
                            if 'related_cases_' in field:
                                idx = field.split('_')[-1]
                                base_name = f"related_case_{idx}"
                            else:
                                base_name = "related_case"
                        else:
                            base_name = field
                        
                        # Add source indicator to filename
                        if source == 'web':
                            base_name = f"{base_name}_web"
                        
                        archive_filename = f"{base_name}{ext}"
                        archive_path = f"{folder_name}/{archive_filename}"
                        
                        # Skip duplicates
                        if archive_path in added_paths:
                            duplicates_skipped += 1
                            continue
                        
                        # Add to ZIP
                        zf.write(cache_path, archive_path)
                        added_paths.add(archive_path)
                        
                        # Track source counts
                        if source == 'api':
                            api_file_count += 1
                        else:
                            web_file_count += 1
                        
                        file_size = file_info.get('file_size', 0)
                        if file_size == 0 and cache_path.exists():
                            file_size = cache_path.stat().st_size
                        
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
                    folder_structure,
                    api_file_count,
                    web_file_count
                )
                zf.writestr('manifest.txt', manifest_content.encode('utf-8'))
    
    processing_time = (datetime.now() - start_time).total_seconds()
    archive_size = ARCHIVE_PATH.stat().st_size
    total_files = sum(files_by_type.values())
    
    # Summary logging
    logger.info(
        f"Archive created: {archive_size / (1024*1024):.1f} MB, "
        f"{persons_count} persons, {total_files} files "
        f"(API: {api_file_count}, Web: {web_file_count})"
    )
    if duplicates_skipped > 0:
        logger.info(f"Duplicates skipped: {duplicates_skipped}")
    if files_not_found > 0:
        logger.info(f"Cache files not found: {files_not_found}")
    
    # Log file type breakdown
    type_summary = ", ".join([f"{ext}: {count}" for ext, count in sorted(files_by_type.items())])
    logger.info(f"Files by type: {type_summary}")
    
    return {
        "status": "success",
        "archive_path": str(ARCHIVE_PATH),
        "archive_size_bytes": archive_size,
        "archive_size_mb": round(archive_size / (1024 * 1024), 2),
        "persons_count": persons_count,
        "total_files": total_files,
        "api_files": api_file_count,
        "web_files": web_file_count,
        "duplicates_skipped": duplicates_skipped,
        "files_not_found": files_not_found,
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
