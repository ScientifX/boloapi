"""
FBI Wanted Data Archive Loader
Loads historical FBI wanted data from archived JSON files into the database.

Usage:
    python load_archive.py

Requirements:
    - JSON files named: wanted_yyyymmddhhmmss.json
    - Files located in: C:\Clients\SD\boloapi\artifacts\fbi_wanted_snapshots
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import execute_values
from psycopg2.extensions import connection as Connection

# Add parent directories to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.join(script_dir, '..', '..')
sys.path.insert(0, os.path.abspath(project_root))

from config import DB_CONFIG
from router_etl import (
    clean_json_recursive,
    parse_date,
    extract_array_field,
    extract_poster_url
    )

# ============================================================================
# CONFIGURATION
# ============================================================================

ARCHIVE_FOLDER = r"C:\Clients\SD\boloapi\artifacts\fbi_wanted_snapshots"
FILENAME_PATTERN = re.compile(r'wanted_(\d{8})\d{6}\.json')

# ============================================================================
# DATABASE HELPERS
# ============================================================================

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

def delete_data_for_date(conn: Connection, pull_date: date) -> int:
    """
    Delete all records for a specific pull_date.
    Returns number of records deleted.
    """
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM tbl_bolo WHERE data_pull_date = %s",
            (pull_date,)
        )
        deleted_count = cur.rowcount
        
        # Also delete metadata
        cur.execute(
            "DELETE FROM api_pull_metadata WHERE pull_date = %s",
            (pull_date,)
        )
        
        return deleted_count

def process_wanted_person(item: Dict, pull_date: date) -> Optional[Dict[str, Any]]:
    """
    Process a single wanted person record into database-ready format.
    Returns None if the record should be skipped.
    """
    uid = item.get('uid')
    if not uid:
        return None

    # Create cleaned version of full_data
    full_data_clean = clean_json_recursive(item)

    return {
        'age_max': item.get('age_max'),
        'age_min': item.get('age_min'),
        'aliases': extract_array_field(item, 'aliases'),
        'build': item.get('build'),
        'caution': item.get('caution'),
        'complexion': item.get('complexion'),
        'coordinates': json.dumps(item.get('coordinates')),
        'data_pull_date': pull_date,
        'dates_of_birth_used': extract_array_field(item, 'dates_of_birth_used'),
        'description': item.get('description'),
        'details': item.get('details'),
        'eyes': item.get('eyes'),
        'eyes_raw': item.get('eyes_raw'),
        'field_offices': extract_array_field(item, 'field_offices'),
        'first_seen_date': pull_date,
        'full_data': json.dumps(item),
        'full_data_clean': json.dumps(full_data_clean),
        'hair': item.get('hair'),
        'hair_raw': item.get('hair_raw'),
        'height_max': item.get('height_max'),
        'height_min': item.get('height_min'),
        'languages': extract_array_field(item, 'languages'),
        'last_seen_date': pull_date,
        'legat_names': extract_array_field(item, 'legat_names'),
        'locations': extract_array_field(item, 'locations'),
        'modified': parse_date(item.get('modified')),
        'nationality': item.get('nationality'),
        'ncic': item.get('ncic'),
        'occupations': extract_array_field(item, 'occupations'),
        'path': item.get('path'),
        'pathid': item.get('pathId'),
        'person_classification': item.get('person_classification'),
        'place_of_birth': item.get('place_of_birth'),
        'possible_countries': extract_array_field(item, 'possible_countries'),
        'possible_states': extract_array_field(item, 'possible_states'),
        'poster_classification': item.get('poster_classification'),
        'poster_url': extract_poster_url(item.get('images', [])),
        'publication': parse_date(item.get('publication')),
        'race': item.get('race'),
        'race_raw': item.get('race_raw'),
        'remarks': item.get('remarks'),
        'reward_max': item.get('reward_max'),
        'reward_min': item.get('reward_min'),
        'reward_text': item.get('reward_text'),
        'scars_and_marks': item.get('scars_and_marks'),
        'sex': item.get('sex'),
        'status': item.get('status'),
        'subjects': extract_array_field(item, 'subjects'),
        'suspects': extract_array_field(item, 'suspects'),
        'title': item.get('title'),
        'uid': uid,
        'url': item.get('url'),
        'warning_message': item.get('warning_message'),
        'weight': item.get('weight'),
        'weight_max': item.get('weight_max'),
        'weight_min': item.get('weight_min'),
        'is_active': True
    }

def insert_api_metadata(conn: Connection, total: int, page: int, pull_date: date):
    """Insert API pull metadata"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO api_pull_metadata (pull_date, total_records, page, pull_timestamp)
            VALUES (%s, %s, %s, %s)
        """, (pull_date, total, page, datetime.combine(pull_date, datetime.min.time())))

def insert_wanted_persons(conn: Connection, records: List[Dict[str, Any]]) -> int:
    """
    Batch insert wanted persons records.
    Returns number of records inserted.
    """
    if not records:
        return 0

    columns = [
        'age_max', 'age_min', 'aliases', 'build', 'caution', 'complexion',
        'coordinates', 'data_pull_date', 'dates_of_birth_used', 'description',
        'details', 'eyes', 'eyes_raw', 'field_offices', 'first_seen_date',
        'full_data', 'full_data_clean', 'hair', 'hair_raw', 'height_max', 'height_min',
        'is_active', 'languages', 'last_seen_date', 'legat_names', 'locations',
        'modified', 'nationality', 'ncic', 'occupations', 'path', 'pathid',
        'person_classification', 'place_of_birth', 'possible_countries',
        'possible_states', 'poster_url', 'poster_classification', 'publication',
        'race', 'race_raw', 'remarks', 'reward_max', 'reward_min', 'reward_text',
        'scars_and_marks', 'sex', 'status', 'subjects', 'suspects', 'title', 'uid',
        'url', 'warning_message', 'weight', 'weight_max', 'weight_min'
    ]

    # Prepare values for batch insert
    values = []
    for record in records:
        row = tuple(record.get(col) for col in columns)
        values.append(row)

    with conn.cursor() as cur:
        insert_query = f"""
            INSERT INTO tbl_bolo (
                age_max, age_min, aliases, build, caution, complexion,
                coordinates, data_pull_date, dates_of_birth_used, description,
                details, eyes, eyes_raw, field_offices, first_seen_date,
                full_data, full_data_clean, hair, hair_raw, height_max, height_min,
                is_active, languages, last_seen_date, legat_names, locations,
                modified, nationality, ncic, occupations, path, pathid,
                person_classification, place_of_birth, possible_countries,
                possible_states, poster_url, poster_classification, publication,
                race, race_raw, remarks, reward_max, reward_min, reward_text,
                scars_and_marks, sex, status, subjects, suspects, title, uid,
                url, warning_message, weight, weight_max, weight_min
            )
            VALUES %s
        """
        execute_values(cur, insert_query, values, page_size=100)
        return cur.rowcount

# ============================================================================
# FILE PROCESSING
# ============================================================================

def extract_date_from_filename(filename: str) -> Optional[date]:
    """
    Extract date from filename in format: wanted_yyyymmddhhmmss.json
    Returns date object or None if pattern doesn't match.
    """
    match = FILENAME_PATTERN.match(filename)
    if not match:
        return None
    
    date_str = match.group(1)  # yyyymmdd
    try:
        return datetime.strptime(date_str, '%Y%m%d').date()
    except ValueError:
        return None

def find_archive_files(folder_path: str) -> List[Tuple[str, date]]:
    """
    Find all archive files in the folder that match the pattern.
    Returns list of (filepath, pull_date) tuples sorted by date.
    """
    folder = Path(folder_path)
    
    if not folder.exists():
        raise FileNotFoundError(f"Archive folder not found: {folder_path}")
    
    files_with_dates = []
    
    for file_path in folder.glob("wanted_*.json"):
        pull_date = extract_date_from_filename(file_path.name)
        if pull_date:
            files_with_dates.append((str(file_path), pull_date))
        else:
            print(f"⚠️  Skipping file with invalid name format: {file_path.name}")
    
    # Sort by date (oldest first)
    files_with_dates.sort(key=lambda x: x[1])
    
    return files_with_dates

def process_archive_file(file_path: str, pull_date: date) -> Dict[str, Any]:
    """
    Process a single archive file.
    Returns summary dict with success status and statistics.
    """
    start_time = datetime.now()
    
    result = {
        'success': False,
        'file_path': file_path,
        'pull_date': str(pull_date),
        'total_in_file': 0,
        'records_deleted': 0,
        'records_inserted': 0,
        'records_skipped': 0,
        'processing_time_seconds': 0,
        'error': None
    }
    
    try:
        # Read JSON file
        print(f"  📄 Reading file: {Path(file_path).name}")
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        total = data.get('total', 0)
        page = data.get('page', 1)
        items = data.get('items', [])
        
        result['total_in_file'] = len(items)
        
        print(f"  📊 Found {len(items)} records (total: {total})")
        
        if not items:
            print(f"  ⚠️  No items in file, skipping")
            result['success'] = True
            result['processing_time_seconds'] = (datetime.now() - start_time).total_seconds()
            return result
        
        # Process records
        print(f"  🔄 Processing records...")
        processed_records = []
        skipped_count = 0
        
        for item in items:
            processed = process_wanted_person(item, pull_date)
            if processed:
                processed_records.append(processed)
            else:
                skipped_count += 1
        
        result['records_skipped'] = skipped_count
        
        # Database operations (DELETE then INSERT)
        print(f"  🗑️  Deleting existing data for {pull_date}...")
        with get_db_connection() as conn:
            # Delete existing records for this date
            deleted_count = delete_data_for_date(conn, pull_date)
            result['records_deleted'] = deleted_count
            print(f"  ✅ Deleted {deleted_count} existing records")
            
            # Insert metadata
            print(f"  💾 Inserting metadata...")
            insert_api_metadata(conn, total, page, pull_date)
            
            # Insert wanted persons
            print(f"  💾 Inserting {len(processed_records)} records...")
            inserted_count = insert_wanted_persons(conn, processed_records)
            result['records_inserted'] = inserted_count
            
            # Commit transaction
            conn.commit()
            print(f"  ✅ Inserted {inserted_count} records")
        
        result['success'] = True
        
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON: {str(e)}"
        print(f"  ❌ {error_msg}")
        result['error'] = error_msg
        
    except FileNotFoundError as e:
        error_msg = f"File not found: {str(e)}"
        print(f"  ❌ {error_msg}")
        result['error'] = error_msg
        
    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        print(f"  ❌ {error_msg}")
        result['error'] = error_msg
    
    finally:
        result['processing_time_seconds'] = round(
            (datetime.now() - start_time).total_seconds(), 2
        )
    
    return result

# ============================================================================
# MAIN EXECUTION
# ============================================================================

def print_section(title: str):
    """Print a formatted section header"""
    print("\n" + "="*80)
    print(f"  {title}")
    print("="*80)

def print_summary(results: List[Dict[str, Any]]):
    """Print summary report"""
    print_section("SUMMARY REPORT")
    
    total_files = len(results)
    successful = sum(1 for r in results if r['success'])
    failed = total_files - successful
    
    total_records_inserted = sum(r['records_inserted'] for r in results)
    total_records_deleted = sum(r['records_deleted'] for r in results)
    total_records_skipped = sum(r['records_skipped'] for r in results)
    total_processing_time = sum(r['processing_time_seconds'] for r in results)
    
    print(f"\n📁 Files Processed:")
    print(f"   Total files found:     {total_files}")
    print(f"   Successfully processed: {successful}")
    print(f"   Failed:                {failed}")
    
    print(f"\n📊 Records:")
    print(f"   Total deleted:  {total_records_deleted:,}")
    print(f"   Total inserted: {total_records_inserted:,}")
    print(f"   Total skipped:  {total_records_skipped:,}")
    
    print(f"\n⏱️  Processing Time:")
    print(f"   Total: {total_processing_time:.2f} seconds")
    print(f"   Average per file: {total_processing_time/total_files:.2f} seconds")
    
    if failed > 0:
        print(f"\n❌ Failed Files:")
        for result in results:
            if not result['success']:
                print(f"   - {Path(result['file_path']).name}")
                print(f"     Date: {result['pull_date']}")
                print(f"     Error: {result['error']}")
    
    print("\n" + "="*80)
    
    if successful == total_files:
        print("✅ ALL FILES PROCESSED SUCCESSFULLY!")
    else:
        print(f"⚠️  {failed} FILE(S) FAILED - See errors above")
    
    print("="*80 + "\n")

def main():
    """Main execution function"""
    print("\n" + "█"*80)
    print("  FBI WANTED DATA ARCHIVE LOADER")
    print("█"*80)
    print(f"\nArchive folder: {ARCHIVE_FOLDER}")
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Find archive files
        print_section("FINDING ARCHIVE FILES")
        files_with_dates = find_archive_files(ARCHIVE_FOLDER)
        
        if not files_with_dates:
            print("❌ No valid archive files found!")
            return
        
        print(f"✅ Found {len(files_with_dates)} archive file(s)")
        print(f"\nDate range: {files_with_dates[0][1]} to {files_with_dates[-1][1]}")
        
        # Process each file
        print_section("PROCESSING FILES")
        results = []
        
        for idx, (file_path, pull_date) in enumerate(files_with_dates, 1):
            print(f"\n[{idx}/{len(files_with_dates)}] Processing: {Path(file_path).name}")
            print(f"  📅 Pull date: {pull_date}")
            
            result = process_archive_file(file_path, pull_date)
            results.append(result)
            
            if result['success']:
                print(f"  ✅ Success - {result['records_inserted']} records inserted in {result['processing_time_seconds']:.2f}s")
            else:
                print(f"  ❌ Failed - {result['error']}")
        
        # Print summary
        print_summary(results)
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Process interrupted by user")
        sys.exit(1)
        
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()