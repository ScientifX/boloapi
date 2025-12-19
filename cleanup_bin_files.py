"""
Cleanup .bin Error Files
=========================
Identifies and removes .bin files that are actually HTML error pages
from the bolo_cache directory, and updates the database accordingly.

These files are typically 403 Forbidden responses from Plone CMS URLs
that block automated requests.

Usage:
    python cleanup_bin_files.py [--dry-run] [--cache-dir PATH]
    
Options:
    --dry-run       Show what would be deleted without actually deleting
    --cache-dir     Path to cache directory (default: data/bolo_cache)
    --size-threshold  Max file size in KB to consider as error page (default: 5)
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Any

import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration - adjust as needed
DB_CONFIG = {
    'dbname': 'postgres',
    'user': 'postgres',
    'password': 'postgres',
    'host': 'localhost',
    'port': 5432,
    'options': '-c search_path=base'
}

# Try to import from config if available
try:
    from config import DB_CONFIG
except ImportError:
    pass


def get_db_connection():
    """Create database connection."""
    return psycopg2.connect(**DB_CONFIG)


def detect_error_page(file_path: Path) -> Tuple[bool, str]:
    """
    Detect if a file is an HTML error page rather than actual content.
    
    Returns:
        Tuple of (is_error_page, reason)
    """
    try:
        # Check file size first - error pages are typically small
        size_kb = file_path.stat().st_size / 1024
        
        if size_kb > 10:
            return False, "file_too_large"
        
        # Read file content
        with open(file_path, 'rb') as f:
            content = f.read(2048)  # Read first 2KB
        
        # Check for HTML markers
        content_lower = content.lower()
        
        # Common error page indicators
        error_indicators = [
            b'<!doctype html',
            b'<html',
            b'403 forbidden',
            b'access denied',
            b'error page',
            b'not found',
            b'<head>',
            b'<body>',
            b'plone',
            b'content-type',
        ]
        
        html_score = sum(1 for indicator in error_indicators if indicator in content_lower)
        
        if html_score >= 2:
            return True, f"html_error_page (score: {html_score})"
        
        # Check if it starts with valid image/PDF magic bytes
        valid_starts = [
            b'\xff\xd8\xff',      # JPEG
            b'\x89PNG',           # PNG
            b'%PDF',              # PDF
            b'GIF8',              # GIF
            b'RIFF',              # WEBP
            b'II*\x00',           # TIFF LE
            b'MM\x00*',           # TIFF BE
        ]
        
        for magic in valid_starts:
            if content.startswith(magic):
                return False, "valid_binary"
        
        # Small file that's not a recognized format - likely error page
        if size_kb < 5:
            return True, "small_unrecognized_file"
        
        return False, "unknown_format"
        
    except Exception as e:
        return False, f"read_error: {e}"


def analyze_bin_files(cache_dir: Path, size_threshold_kb: float = 5.0) -> Dict[str, Any]:
    """
    Analyze all .bin files in the cache directory.
    
    Returns:
        Analysis results with categorized files
    """
    results = {
        'total_bin_files': 0,
        'error_pages': [],
        'valid_files': [],
        'read_errors': [],
        'total_size_bytes': 0,
        'error_size_bytes': 0,
    }
    
    bin_files = list(cache_dir.glob('*.bin'))
    results['total_bin_files'] = len(bin_files)
    
    for file_path in bin_files:
        try:
            file_size = file_path.stat().st_size
            results['total_size_bytes'] += file_size
            
            is_error, reason = detect_error_page(file_path)
            
            file_info = {
                'path': file_path,
                'filename': file_path.name,
                'size_bytes': file_size,
                'size_kb': round(file_size / 1024, 2),
                'reason': reason,
            }
            
            if is_error:
                results['error_pages'].append(file_info)
                results['error_size_bytes'] += file_size
            else:
                results['valid_files'].append(file_info)
                
        except Exception as e:
            results['read_errors'].append({
                'path': file_path,
                'filename': file_path.name,
                'error': str(e)
            })
    
    return results


def get_cache_path_to_url_mapping(conn) -> Dict[str, Dict[str, Any]]:
    """Get mapping of cache_path to URL info from database."""
    mapping = {}
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT link_id, uid, field, actual_url, cache_path, result
            FROM tbl_bolo_link_check
            WHERE cache_path IS NOT NULL
              AND cache_path LIKE '%%.bin'
        """)
        
        for row in cur.fetchall():
            cache_path = row['cache_path']
            # Extract just the filename from the path
            filename = Path(cache_path).name
            mapping[filename] = dict(row)
    
    return mapping


def update_database_records(conn, error_files: List[Dict], dry_run: bool = False) -> int:
    """
    Update database records for error files.
    Sets result to 'plone_blocked' and clears cache info.
    
    Returns:
        Number of records updated
    """
    if not error_files:
        return 0
    
    # Get the cache_path to URL mapping
    mapping = get_cache_path_to_url_mapping(conn)
    
    updated = 0
    
    with conn.cursor() as cur:
        for file_info in error_files:
            filename = file_info['filename']
            
            if filename in mapping:
                record = mapping[filename]
                
                if dry_run:
                    print(f"  Would update: {record['actual_url'][:60]}...")
                    updated += 1
                else:
                    cur.execute("""
                        UPDATE tbl_bolo_link_check
                        SET result = 'plone_blocked',
                            cache_path = NULL,
                            file_size = NULL,
                            cached_at = NULL,
                            updated_at = NOW()
                        WHERE link_id = %s
                    """, (record['link_id'],))
                    updated += 1
        
        if not dry_run:
            conn.commit()
    
    return updated


def delete_error_files(error_files: List[Dict], dry_run: bool = False) -> Tuple[int, int]:
    """
    Delete error files from disk.
    
    Returns:
        Tuple of (files_deleted, bytes_freed)
    """
    deleted = 0
    bytes_freed = 0
    
    for file_info in error_files:
        file_path = file_info['path']
        
        if dry_run:
            print(f"  Would delete: {file_path.name} ({file_info['size_kb']} KB)")
            deleted += 1
            bytes_freed += file_info['size_bytes']
        else:
            try:
                file_path.unlink()
                deleted += 1
                bytes_freed += file_info['size_bytes']
            except Exception as e:
                print(f"  Error deleting {file_path.name}: {e}")
    
    return deleted, bytes_freed


def main():
    parser = argparse.ArgumentParser(description='Clean up .bin error files from cache')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done without making changes')
    parser.add_argument('--cache-dir', type=str, default='data/bolo_cache',
                        help='Path to cache directory')
    parser.add_argument('--size-threshold', type=float, default=5.0,
                        help='Max file size in KB to consider as error page')
    parser.add_argument('--skip-db', action='store_true',
                        help='Skip database updates, only delete files')
    args = parser.parse_args()
    
    cache_dir = Path(args.cache_dir)
    
    if not cache_dir.exists():
        print(f"ERROR: Cache directory not found: {cache_dir}")
        sys.exit(1)
    
    print("=" * 60)
    print("BIN FILE CLEANUP UTILITY")
    print("=" * 60)
    print(f"Cache directory: {cache_dir}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print(f"Size threshold: {args.size_threshold} KB")
    print("-" * 60)
    
    # Analyze files
    print("\nAnalyzing .bin files...")
    results = analyze_bin_files(cache_dir, args.size_threshold)
    
    print(f"\n--- ANALYSIS RESULTS ---")
    print(f"Total .bin files:     {results['total_bin_files']}")
    print(f"Error pages found:    {len(results['error_pages'])}")
    print(f"Valid files:          {len(results['valid_files'])}")
    print(f"Read errors:          {len(results['read_errors'])}")
    print(f"Total size:           {results['total_size_bytes'] / 1024:.2f} KB")
    print(f"Error page size:      {results['error_size_bytes'] / 1024:.2f} KB")
    
    if not results['error_pages']:
        print("\nNo error pages found. Nothing to clean up.")
        return
    
    # Show sample of what will be deleted
    print(f"\n--- SAMPLE ERROR PAGES (first 5) ---")
    for f in results['error_pages'][:5]:
        print(f"  {f['filename']} - {f['size_kb']} KB - {f['reason']}")
    
    if len(results['error_pages']) > 5:
        print(f"  ... and {len(results['error_pages']) - 5} more")
    
    # Update database
    if not args.skip_db:
        print(f"\n--- DATABASE UPDATES ---")
        try:
            conn = get_db_connection()
            db_updated = update_database_records(conn, results['error_pages'], args.dry_run)
            print(f"Records {'to update' if args.dry_run else 'updated'}: {db_updated}")
            conn.close()
        except Exception as e:
            print(f"Database error: {e}")
            print("Continuing with file deletion...")
    
    # Delete files
    print(f"\n--- FILE DELETION ---")
    deleted, bytes_freed = delete_error_files(results['error_pages'], args.dry_run)
    
    print(f"\n--- SUMMARY ---")
    print(f"Files {'to delete' if args.dry_run else 'deleted'}:  {deleted}")
    print(f"Space {'to free' if args.dry_run else 'freed'}:    {bytes_freed / 1024:.2f} KB ({bytes_freed / (1024*1024):.2f} MB)")
    
    if args.dry_run:
        print("\n*** DRY RUN - No changes were made ***")
        print("Run without --dry-run to apply changes.")
    else:
        print("\nCleanup complete!")


if __name__ == '__main__':
    main()
