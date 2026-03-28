"""
service_merge_etl.py - Merge ETL Service for tbl_bolo_full

This module merges FBI wanted persons records from two sources:
- tbl_bolo (API source) - Rich but potentially stale data
- tbl_bolo_web (Web source) - Fresh but potentially sparse data

Merge Rules:
- Scalar fields: Web value wins if populated, else API value
- Array fields: UNION with deduplication
- JSONB fields: Deep merge with same rules
- A record is inactive if removed from EITHER source

The merged records are stored in tbl_bolo_full with full provenance tracking.
"""

import json
import logging
import hashlib
from datetime import datetime, date
from typing import Dict, Any, List, Optional, Tuple, Set
from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.extensions import connection as Connection

from config import DB_CONFIG
from utils_warning_enrichment import enrich_with_warning_components

# Set up logging
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Fields to exclude from content hash (volatile fields)
VOLATILE_HASH_FIELDS = {'modified', '@id'}


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
# HELPER FUNCTIONS: Populated checks
# =============================================================================

def is_populated_text(val: Any) -> bool:
    """Check if a text value is meaningfully populated."""
    if val is None:
        return False
    if not isinstance(val, str):
        return True  # Non-string, consider populated
    return val.strip() != ''


def is_populated_array(val: Any) -> bool:
    """Check if an array value is meaningfully populated."""
    if val is None:
        return False
    if not isinstance(val, (list, tuple)):
        return False
    return len(val) > 0


def is_populated_jsonb(val: Any) -> bool:
    """Check if a JSONB value is meaningfully populated."""
    if val is None:
        return False
    if isinstance(val, dict):
        return len(val) > 0
    if isinstance(val, list):
        return len(val) > 0
    return True


def is_populated(val: Any) -> bool:
    """Generic populated check."""
    if val is None:
        return False
    if isinstance(val, str):
        return is_populated_text(val)
    if isinstance(val, (list, tuple)):
        return is_populated_array(val)
    if isinstance(val, dict):
        return is_populated_jsonb(val)
    return True


# =============================================================================
# MERGE FUNCTIONS: Scalar fields
# =============================================================================

def merge_scalar(api_val: Any, web_val: Any) -> Tuple[Any, Optional[str]]:
    """
    Merge scalar values: Web wins if populated, else API.
    Returns (merged_value, source_used).
    """
    if is_populated(web_val):
        return web_val, 'WEB'
    elif is_populated(api_val):
        return api_val, 'API'
    else:
        return None, None


def merge_timestamp(api_val: Any, web_val: Any, prefer_recent: bool = False) -> Tuple[Any, Optional[str]]:
    """
    Merge timestamp values.
    If prefer_recent=True, take the more recent timestamp.
    Otherwise, web wins if populated.
    """
    if prefer_recent and api_val is not None and web_val is not None:
        # Compare timestamps, take more recent
        if web_val > api_val:
            return web_val, 'WEB'
        else:
            return api_val, 'API'
    
    # Standard merge: web wins if populated
    return merge_scalar(api_val, web_val)


# =============================================================================
# MERGE FUNCTIONS: Array fields
# =============================================================================

def merge_array(api_val: Optional[List], web_val: Optional[List]) -> Tuple[Optional[List], Optional[str]]:
    """
    Merge arrays: UNION with deduplication.
    Returns (merged_array, source_used).
    """
    api_populated = is_populated_array(api_val)
    web_populated = is_populated_array(web_val)
    
    if web_populated and api_populated:
        # UNION: combine unique values, preserving order (web first)
        seen = set()
        merged = []
        
        # Add web values first
        for item in web_val:
            if item is not None and item not in seen:
                seen.add(item)
                merged.append(item)
        
        # Add API values not already present
        for item in api_val:
            if item is not None and item not in seen:
                seen.add(item)
                merged.append(item)
        
        return merged if merged else None, 'BOTH'
    
    elif web_populated:
        return list(web_val), 'WEB'
    
    elif api_populated:
        return list(api_val), 'API'
    
    else:
        return None, None


# =============================================================================
# MERGE FUNCTIONS: JSONB deep merge
# =============================================================================

def merge_jsonb_deep(api_data: Optional[Dict], web_data: Optional[Dict]) -> Dict:
    """
    Deep merge two JSONB objects.
    - Scalars: Web wins if populated
    - Arrays: UNION
    - Objects: Recursive merge
    - 'modified' field: Take more recent
    """
    if api_data is None and web_data is None:
        return {}
    if api_data is None:
        return web_data or {}
    if web_data is None:
        return api_data or {}
    
    result = {}
    all_keys = set(api_data.keys()) | set(web_data.keys())
    
    for key in all_keys:
        api_val = api_data.get(key)
        web_val = web_data.get(key)
        
        # Special handling for 'modified': take more recent
        if key == 'modified':
            merged, _ = merge_timestamp(api_val, web_val, prefer_recent=True)
            if merged is not None:
                result[key] = merged
        
        # Arrays: UNION
        elif isinstance(api_val, list) or isinstance(web_val, list):
            merged, _ = merge_jsonb_arrays(api_val, web_val)
            if merged is not None:
                result[key] = merged
        
        # Nested objects: recursive merge
        elif isinstance(api_val, dict) or isinstance(web_val, dict):
            merged = merge_jsonb_deep(
                api_val if isinstance(api_val, dict) else None,
                web_val if isinstance(web_val, dict) else None
            )
            if merged:
                result[key] = merged
        
        # Scalars: web wins if populated
        else:
            merged, _ = merge_scalar(api_val, web_val)
            if merged is not None:
                result[key] = merged
    
    return result


def merge_jsonb_arrays(api_arr: Optional[List], web_arr: Optional[List]) -> Tuple[Optional[List], Optional[str]]:
    """
    Merge JSONB arrays (arrays of objects like files, images).
    Uses full object equality for deduplication.
    """
    api_populated = isinstance(api_arr, list) and len(api_arr) > 0
    web_populated = isinstance(web_arr, list) and len(web_arr) > 0
    
    if web_populated and api_populated:
        # UNION with object equality
        seen = []
        merged = []
        
        for item in (web_arr + api_arr):
            # Convert to JSON string for comparison
            item_str = json.dumps(item, sort_keys=True) if isinstance(item, dict) else str(item)
            if item_str not in seen:
                seen.append(item_str)
                merged.append(item)
        
        return merged if merged else None, 'BOTH'
    
    elif web_populated:
        return list(web_arr), 'WEB'
    
    elif api_populated:
        return list(api_arr), 'API'
    
    else:
        return None, None


# =============================================================================
# MAIN RECORD MERGE FUNCTION
# =============================================================================

def merge_bolo_records(
    api_record: Optional[Dict[str, Any]], 
    web_record: Optional[Dict[str, Any]],
    merge_date: date
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Merge complete BOLO records from API and Web sources.
    
    Args:
        api_record: Record from tbl_bolo (or None if not exists)
        web_record: Record from tbl_bolo_web (or None if not exists)
        merge_date: Date of this merge operation
    
    Returns:
        Tuple of (merged_record, merge_stats)
    """
    field_sources = {}
    
    # Determine source flags
    api_exists = api_record is not None and api_record.get('uid') is not None
    web_exists = web_record is not None and web_record.get('uid') is not None
    
    if api_exists and web_exists:
        source_flags = 'BOTH'
    elif web_exists:
        source_flags = 'WEB'
    elif api_exists:
        source_flags = 'API'
    else:
        return None, {'error': 'No valid source records'}
    
    # Initialize with empty values
    api_record = api_record or {}
    web_record = web_record or {}
    
    merged = {
        'source_flags': source_flags,
        'merge_date': merge_date,
    }
    
    # =========================================================================
    # SCALAR TEXT FIELDS
    # =========================================================================
    text_fields = [
        'build', 'caution', 'complexion', 'description', 'details',
        'eyes', 'eyes_raw', 'hair', 'hair_raw', 'nationality', 'ncic',
        'path', 'pathid', 'person_classification', 'place_of_birth',
        'poster_classification', 'poster_url', 'race', 'race_raw',
        'remarks', 'reward_text', 'scars_and_marks', 'sex', 'status',
        'title', 'url', 'warning_message', 'weight'
    ]
    
    for field in text_fields:
        merged_val, source = merge_scalar(api_record.get(field), web_record.get(field))
        merged[field] = merged_val
        if source:
            field_sources[field] = source
    
    # =========================================================================
    # SCALAR INTEGER FIELDS
    # =========================================================================
    int_fields = [
        'age_max', 'age_min', 'height_max', 'height_min',
        'reward_max', 'reward_min', 'weight_max', 'weight_min'
    ]
    
    for field in int_fields:
        merged_val, source = merge_scalar(api_record.get(field), web_record.get(field))
        merged[field] = merged_val
        if source:
            field_sources[field] = source
    
    # =========================================================================
    # TIMESTAMP FIELDS
    # =========================================================================
    # publication: standard merge
    merged_val, source = merge_scalar(api_record.get('publication'), web_record.get('publication'))
    merged['publication'] = merged_val
    if source:
        field_sources['publication'] = source
    
    # modified: take more recent
    merged_val, source = merge_timestamp(
        api_record.get('modified'), 
        web_record.get('modified'), 
        prefer_recent=True
    )
    merged['modified'] = merged_val
    if source:
        field_sources['modified'] = source
    
    # was_captured: standard merge
    merged_val, source = merge_scalar(api_record.get('was_captured'), web_record.get('was_captured'))
    merged['was_captured'] = merged_val
    if source:
        field_sources['was_captured'] = source
    
    # =========================================================================
    # JSONB SCALAR (coordinates)
    # =========================================================================
    merged_val, source = merge_scalar(api_record.get('coordinates'), web_record.get('coordinates'))
    merged['coordinates'] = merged_val
    if source:
        field_sources['coordinates'] = source
    
    # =========================================================================
    # ARRAY FIELDS (UNION)
    # =========================================================================
    array_fields = [
        'aliases', 'dates_of_birth_used', 'field_offices', 'languages',
        'legat_names', 'locations', 'occupations', 'possible_countries',
        'possible_states', 'subjects', 'suspects', 'related_cases'
    ]
    
    for field in array_fields:
        merged_val, source = merge_array(api_record.get(field), web_record.get(field))
        merged[field] = merged_val
        if source:
            field_sources[field] = source
    
    # =========================================================================
    # JSONB DEEP MERGE (full_data, full_data_clean)
    # =========================================================================
    merged_full_data = merge_jsonb_deep(
        api_record.get('full_data'),
        web_record.get('full_data')
    )
    merged['full_data'] = merged_full_data
    field_sources['full_data'] = 'MERGED'
    
    merged_full_data_clean = merge_jsonb_deep(
        api_record.get('full_data_clean'),
        web_record.get('full_data_clean')
    )
    
    # Re-enrich with warning components
    try:
        merged_full_data_clean = enrich_with_warning_components(merged_full_data_clean)
    except Exception as e:
        logger.warning(f"Warning enrichment failed: {e}")
    
    merged['full_data_clean'] = merged_full_data_clean
    field_sources['full_data_clean'] = 'MERGED'
    
    # =========================================================================
    # METADATA FIELDS
    # =========================================================================
    # UID comes from whichever exists
    merged['uid'] = web_record.get('uid') or api_record.get('uid')
    
    # first_seen_date: MIN (earliest sighting)
    api_first = api_record.get('first_seen_date')
    web_first = web_record.get('first_seen_date')
    if api_first and web_first:
        merged['first_seen_date'] = min(api_first, web_first)
    else:
        merged['first_seen_date'] = api_first or web_first
    
    # last_seen_date: MAX (most recent sighting)
    api_last = api_record.get('last_seen_date')
    web_last = web_record.get('last_seen_date')
    if api_last and web_last:
        merged['last_seen_date'] = max(api_last, web_last)
    else:
        merged['last_seen_date'] = api_last or web_last
    
    # Store provenance info
    merged['field_sources'] = field_sources
    merged['api_content_hash'] = api_record.get('content_hash') if api_exists else None
    merged['web_content_hash'] = web_record.get('content_hash') if web_exists else None
    merged['api_version'] = api_record.get('version_number') if api_exists else None
    merged['web_version'] = web_record.get('version_number') if web_exists else None
    merged['api_last_seen'] = api_record.get('last_seen_date') if api_exists else None
    merged['web_last_seen'] = web_record.get('last_seen_date') if web_exists else None
    
    # Compute content hash for merged record
    merged['content_hash'] = compute_merged_content_hash(merged_full_data_clean)
    
    # Build merge stats
    merge_stats = {
        'source_flags': source_flags,
        'api_exists': api_exists,
        'web_exists': web_exists,
        'total_fields_merged': len(field_sources),
        'fields_from_api': sum(1 for v in field_sources.values() if v == 'API'),
        'fields_from_web': sum(1 for v in field_sources.values() if v == 'WEB'),
        'fields_from_both': sum(1 for v in field_sources.values() if v == 'BOTH'),
        'fields_merged': sum(1 for v in field_sources.values() if v == 'MERGED'),
    }
    
    return merged, merge_stats


def compute_merged_content_hash(full_data_clean: Dict) -> str:
    """
    Compute SHA-256 hash of merged data, excluding volatile fields.
    """
    if not full_data_clean:
        return hashlib.sha256(b'{}').hexdigest()
    
    # Create copy without volatile fields
    hashable_data = {k: v for k, v in full_data_clean.items() 
                     if k not in VOLATILE_HASH_FIELDS}
    
    # Stable JSON serialization
    json_str = json.dumps(hashable_data, sort_keys=True, default=str)
    
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()


# =============================================================================
# DATABASE OPERATIONS
# =============================================================================

def get_all_active_uids(conn: Connection) -> Dict[str, Dict[str, bool]]:
    """
    Get all active UIDs from both source tables.
    Returns dict: {uid: {'api': bool, 'web': bool}}
    """
    uid_map = {}
    
    with conn.cursor() as cur:
        # Get API active UIDs
        cur.execute("""
            SELECT DISTINCT uid 
            FROM base.tbl_bolo 
            WHERE valid_to IS NULL 
              AND is_active = TRUE 
              AND change_type <> 'REMOVED'
        """)
        for row in cur.fetchall():
            uid = row[0]
            uid_map[uid] = {'api': True, 'web': False}
        
        # Get Web active UIDs
        cur.execute("""
            SELECT DISTINCT uid 
            FROM base.tbl_bolo_web 
            WHERE valid_to IS NULL 
              AND is_active = TRUE 
              AND change_type <> 'REMOVED'
        """)
        for row in cur.fetchall():
            uid = row[0]
            if uid in uid_map:
                uid_map[uid]['web'] = True
            else:
                uid_map[uid] = {'api': False, 'web': True}
    
    return uid_map


def get_source_record(conn: Connection, uid: str, source: str) -> Optional[Dict[str, Any]]:
    """
    Fetch active record from specified source table.
    source: 'api' or 'web'
    """
    table = 'base.tbl_bolo' if source == 'api' else 'base.tbl_bolo_web'
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"""
            SELECT * FROM {table}
            WHERE uid = %s 
              AND valid_to IS NULL 
              AND is_active = TRUE 
              AND change_type <> 'REMOVED'
            LIMIT 1
        """, (uid,))
        result = cur.fetchone()
        return dict(result) if result else None


def get_current_merged_record(conn: Connection, uid: str) -> Optional[Dict[str, Any]]:
    """
    Fetch current active record from tbl_bolo_full.
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT * FROM base.tbl_bolo_full
            WHERE uid = %s 
              AND valid_to IS NULL 
              AND is_active = TRUE 
              AND change_type <> 'REMOVED'
            LIMIT 1
        """, (uid,))
        result = cur.fetchone()
        return dict(result) if result else None


def get_next_version_number(conn: Connection, uid: str) -> int:
    """Get next version number for a UID in tbl_bolo_full."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(MAX(version_number), 0) + 1 
            FROM base.tbl_bolo_full 
            WHERE uid = %s
        """, (uid,))
        return cur.fetchone()[0]


def was_previously_removed(conn: Connection, uid: str) -> bool:
    """Check if this UID was previously marked as REMOVED."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM base.tbl_bolo_full 
            WHERE uid = %s AND change_type = 'REMOVED'
            LIMIT 1
        """, (uid,))
        return cur.fetchone() is not None


def close_current_version(conn: Connection, uid: str, close_date: date) -> None:
    """Close the current active version for a UID."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE base.tbl_bolo_full
            SET valid_to = %s,
                is_active = FALSE,
                updated_at = NOW()
            WHERE uid = %s AND valid_to IS NULL
        """, (close_date, uid))


def insert_merged_record(
    conn: Connection, 
    merged: Dict[str, Any], 
    version_number: int,
    change_type: str,
    merge_date: date
) -> None:
    """Insert a new merged record into tbl_bolo_full."""
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO base.tbl_bolo_full (
                uid, content_hash, version_number, valid_from, valid_to,
                change_type, is_active, first_seen_date, last_seen_date, merge_date,
                source_flags, api_content_hash, web_content_hash,
                api_version, web_version, api_last_seen, web_last_seen,
                field_sources, merge_timestamp,
                age_max, age_min, aliases, build, caution, complexion,
                coordinates, dates_of_birth_used, description, details,
                eyes, eyes_raw, field_offices, hair, hair_raw,
                height_max, height_min, languages, legat_names, locations,
                modified, nationality, ncic, occupations, path, pathid,
                person_classification, place_of_birth, possible_countries,
                possible_states, poster_classification, poster_url,
                publication, race, race_raw, related_cases, remarks,
                reward_max, reward_min, reward_text, scars_and_marks,
                sex, status, subjects, suspects, title, url,
                warning_message, was_captured, weight, weight_max, weight_min,
                full_data, full_data_clean
            ) VALUES (
                %s, %s, %s, %s, NULL,
                %s, TRUE, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, NOW(),
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s
            )
        """, (
            merged['uid'],
            merged['content_hash'],
            version_number,
            merge_date,
            change_type,
            merged['first_seen_date'],
            merged['last_seen_date'],
            merge_date,
            merged['source_flags'],
            merged.get('api_content_hash'),
            merged.get('web_content_hash'),
            merged.get('api_version'),
            merged.get('web_version'),
            merged.get('api_last_seen'),
            merged.get('web_last_seen'),
            json.dumps(merged.get('field_sources', {})),
            merged.get('age_max'),
            merged.get('age_min'),
            merged.get('aliases'),
            merged.get('build'),
            merged.get('caution'),
            merged.get('complexion'),
            json.dumps(merged.get('coordinates')) if merged.get('coordinates') else None,
            merged.get('dates_of_birth_used'),
            merged.get('description'),
            merged.get('details'),
            merged.get('eyes'),
            merged.get('eyes_raw'),
            merged.get('field_offices'),
            merged.get('hair'),
            merged.get('hair_raw'),
            merged.get('height_max'),
            merged.get('height_min'),
            merged.get('languages'),
            merged.get('legat_names'),
            merged.get('locations'),
            merged.get('modified'),
            merged.get('nationality'),
            merged.get('ncic'),
            merged.get('occupations'),
            merged.get('path'),
            merged.get('pathid'),
            merged.get('person_classification'),
            merged.get('place_of_birth'),
            merged.get('possible_countries'),
            merged.get('possible_states'),
            merged.get('poster_classification'),
            merged.get('poster_url'),
            merged.get('publication'),
            merged.get('race'),
            merged.get('race_raw'),
            merged.get('related_cases'),
            merged.get('remarks'),
            merged.get('reward_max'),
            merged.get('reward_min'),
            merged.get('reward_text'),
            merged.get('scars_and_marks'),
            merged.get('sex'),
            merged.get('status'),
            merged.get('subjects'),
            merged.get('suspects'),
            merged.get('title'),
            merged.get('url'),
            merged.get('warning_message'),
            merged.get('was_captured'),
            merged.get('weight'),
            merged.get('weight_max'),
            merged.get('weight_min'),
            json.dumps(merged.get('full_data', {})),
            json.dumps(merged.get('full_data_clean', {}))
        ))


def mark_uid_removed(conn: Connection, uid: str, merge_date: date) -> None:
    """
    Mark a UID as REMOVED in tbl_bolo_full.
    Close current version and insert tombstone.
    """
    # Get current record info for tombstone
    current = get_current_merged_record(conn, uid)
    if not current:
        return
    
    # Close current version
    close_current_version(conn, uid, merge_date)
    
    # Insert tombstone
    version_number = get_next_version_number(conn, uid)
    
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE base.tbl_bolo_full
            SET became_inactive_at = NOW()
            WHERE uid = %s AND valid_to = %s
        """, (uid, merge_date))
        
        # Create tombstone record
        tombstone_data = {
            'uid': uid,
            'removed_date': str(merge_date),
            'previous_version': version_number - 1
        }
        tombstone_hash = hashlib.sha256(
            json.dumps(tombstone_data, sort_keys=True).encode('utf-8')
        ).hexdigest()
        
        cur.execute("""
            INSERT INTO base.tbl_bolo_full (
                uid, content_hash, version_number, valid_from, valid_to,
                change_type, is_active, first_seen_date, last_seen_date, merge_date,
                source_flags, field_sources, merge_timestamp,
                title, full_data, full_data_clean, became_inactive_at
            ) VALUES (
                %s, %s, %s, %s, NULL,
                'REMOVED', FALSE, %s, %s, %s,
                %s, %s, NOW(),
                %s, %s, %s, NOW()
            )
        """, (
            uid,
            tombstone_hash,
            version_number,
            merge_date,
            current.get('first_seen_date') or merge_date,
            merge_date,
            merge_date,
            current.get('source_flags', 'UNKNOWN'),
            json.dumps({}),
            current.get('title'),
            json.dumps(current.get('full_data', {})),
            json.dumps(current.get('full_data_clean', {}))
        ))


def get_active_merged_uids(conn: Connection) -> Set[str]:
    """Get set of all active UIDs in tbl_bolo_full."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT uid FROM base.tbl_bolo_full
            WHERE valid_to IS NULL 
              AND is_active = TRUE 
              AND change_type <> 'REMOVED'
        """)
        return {row[0] for row in cur.fetchall()}


def insert_merge_metadata(
    conn: Connection,
    merge_date: date,
    stats: Dict[str, Any]
) -> None:
    """Insert merge ETL metadata into tbl_bolo_control_full."""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO base.tbl_bolo_control_full (
                merge_date, merge_timestamp,
                api_active_count, web_active_count,
                records_api_only, records_web_only, records_both_sources,
                records_new, records_modified, records_unchanged, 
                records_removed, records_returned,
                active_count, inactive_count, total_versions,
                processing_time_seconds,
                fields_from_api, fields_from_web, arrays_merged,
                errors
            ) VALUES (
                %s, NOW(),
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s,
                %s, %s, %s,
                %s
            )
            ON CONFLICT (merge_date) DO UPDATE SET
                merge_timestamp = NOW(),
                api_active_count = EXCLUDED.api_active_count,
                web_active_count = EXCLUDED.web_active_count,
                records_api_only = EXCLUDED.records_api_only,
                records_web_only = EXCLUDED.records_web_only,
                records_both_sources = EXCLUDED.records_both_sources,
                records_new = EXCLUDED.records_new,
                records_modified = EXCLUDED.records_modified,
                records_unchanged = EXCLUDED.records_unchanged,
                records_removed = EXCLUDED.records_removed,
                records_returned = EXCLUDED.records_returned,
                active_count = EXCLUDED.active_count,
                inactive_count = EXCLUDED.inactive_count,
                total_versions = EXCLUDED.total_versions,
                processing_time_seconds = EXCLUDED.processing_time_seconds,
                fields_from_api = EXCLUDED.fields_from_api,
                fields_from_web = EXCLUDED.fields_from_web,
                arrays_merged = EXCLUDED.arrays_merged,
                errors = EXCLUDED.errors
        """, (
            merge_date,
            stats.get('api_active_count', 0),
            stats.get('web_active_count', 0),
            stats.get('records_api_only', 0),
            stats.get('records_web_only', 0),
            stats.get('records_both_sources', 0),
            stats.get('records_new', 0),
            stats.get('records_modified', 0),
            stats.get('records_unchanged', 0),
            stats.get('records_removed', 0),
            stats.get('records_returned', 0),
            stats.get('active_count', 0),
            stats.get('inactive_count', 0),
            stats.get('total_versions', 0),
            stats.get('processing_time_seconds', 0),
            stats.get('fields_from_api', 0),
            stats.get('fields_from_web', 0),
            stats.get('arrays_merged', 0),
            json.dumps(stats.get('errors', []))
        ))


def get_final_counts(conn: Connection) -> Dict[str, int]:
    """Get final active/inactive counts from tbl_bolo_full."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE valid_to IS NULL AND is_active = TRUE AND change_type <> 'REMOVED') as active_count,
                COUNT(*) FILTER (WHERE valid_to IS NOT NULL OR is_active = FALSE OR change_type = 'REMOVED') as inactive_count,
                COUNT(*) as total_versions,
                COUNT(DISTINCT uid) as unique_uids
            FROM base.tbl_bolo_full
        """)
        result = cur.fetchone()
        return {
            'active_count': result[0] or 0,
            'inactive_count': result[1] or 0,
            'total_versions': result[2] or 0,
            'unique_uids': result[3] or 0
        }


# =============================================================================
# MAIN ETL FUNCTION
# =============================================================================

def import_data_set_full(merge_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Main merge ETL function - merges API and Web data into tbl_bolo_full.
    
    Args:
        merge_date: Date for this merge (defaults to today)
    
    Returns:
        Dictionary with merge statistics and results
    """
    start_time = datetime.now()
    merge_date = merge_date or date.today()
    
    # Statistics
    stats = {
        'api_active_count': 0,
        'web_active_count': 0,
        'records_api_only': 0,
        'records_web_only': 0,
        'records_both_sources': 0,
        'records_new': 0,
        'records_modified': 0,
        'records_unchanged': 0,
        'records_removed': 0,
        'records_returned': 0,
        'fields_from_api': 0,
        'fields_from_web': 0,
        'arrays_merged': 0,
        'errors': []
    }
    
    try:
        with get_db_connection() as conn:
            logger.info(f"Starting merge ETL for date {merge_date}")
            
            # Step 1: Get all active UIDs from both sources
            logger.info("Step 1: Getting active UIDs from both sources")
            uid_map = get_all_active_uids(conn)
            
            # Count source distribution
            for uid, sources in uid_map.items():
                if sources['api']:
                    stats['api_active_count'] += 1
                if sources['web']:
                    stats['web_active_count'] += 1
                if sources['api'] and sources['web']:
                    stats['records_both_sources'] += 1
                elif sources['api']:
                    stats['records_api_only'] += 1
                else:
                    stats['records_web_only'] += 1
            
            logger.info(f"Found {len(uid_map)} unique UIDs: "
                       f"{stats['records_api_only']} API-only, "
                       f"{stats['records_web_only']} Web-only, "
                       f"{stats['records_both_sources']} in both")
            
            # Step 2: Get currently active merged UIDs
            current_merged_uids = get_active_merged_uids(conn)
            logger.info(f"Current merged table has {len(current_merged_uids)} active UIDs")
            
            # Step 3: Process each UID
            logger.info("Step 2: Processing UIDs")
            processed = 0
            
            for uid, sources in uid_map.items():
                try:
                    # Fetch source records
                    api_record = get_source_record(conn, uid, 'api') if sources['api'] else None
                    web_record = get_source_record(conn, uid, 'web') if sources['web'] else None
                    
                    # Merge records
                    merged, merge_stats = merge_bolo_records(api_record, web_record, merge_date)
                    
                    if merged is None:
                        logger.warning(f"Merge returned None for UID {uid}")
                        stats['errors'].append(f"Merge failed for {uid}")
                        continue
                    
                    # Track field statistics
                    stats['fields_from_api'] += merge_stats.get('fields_from_api', 0)
                    stats['fields_from_web'] += merge_stats.get('fields_from_web', 0)
                    stats['arrays_merged'] += merge_stats.get('fields_from_both', 0)
                    
                    # Check against current merged record
                    current = get_current_merged_record(conn, uid)
                    
                    if current is None:
                        # New record
                        was_removed = was_previously_removed(conn, uid)
                        change_type = 'RETURNED' if was_removed else 'NEW'
                        version = get_next_version_number(conn, uid)
                        
                        insert_merged_record(conn, merged, version, change_type, merge_date)
                        
                        if was_removed:
                            stats['records_returned'] += 1
                        else:
                            stats['records_new'] += 1
                    
                    elif current['content_hash'] != merged['content_hash']:
                        # Content changed - insert new version
                        close_current_version(conn, uid, merge_date)
                        version = get_next_version_number(conn, uid)
                        
                        insert_merged_record(conn, merged, version, 'MODIFIED', merge_date)
                        stats['records_modified'] += 1
                    
                    else:
                        # Content unchanged - just update last_seen_date
                        with conn.cursor() as cur:
                            cur.execute("""
                                UPDATE base.tbl_bolo_full
                                SET last_seen_date = %s,
                                    updated_at = NOW(),
                                    api_last_seen = %s,
                                    web_last_seen = %s
                                WHERE uid = %s AND valid_to IS NULL
                            """, (
                                merged['last_seen_date'],
                                merged.get('api_last_seen'),
                                merged.get('web_last_seen'),
                                uid
                            ))
                        stats['records_unchanged'] += 1
                    
                    processed += 1
                    if processed % 100 == 0:
                        logger.info(f"Processed {processed}/{len(uid_map)} UIDs")
                        conn.commit()  # Periodic commit
                
                except Exception as e:
                    logger.error(f"Error processing UID {uid}: {e}")
                    stats['errors'].append(f"Error processing {uid}: {str(e)}")
            
            # Step 4: Mark removed UIDs
            logger.info("Step 3: Marking removed UIDs")
            active_source_uids = set(uid_map.keys())
            removed_uids = current_merged_uids - active_source_uids
            
            for uid in removed_uids:
                try:
                    mark_uid_removed(conn, uid, merge_date)
                    stats['records_removed'] += 1
                except Exception as e:
                    logger.error(f"Error marking {uid} as removed: {e}")
                    stats['errors'].append(f"Error removing {uid}: {str(e)}")
            
            logger.info(f"Marked {len(removed_uids)} UIDs as removed")
            
            # Step 5: Get final counts
            final_counts = get_final_counts(conn)
            stats.update(final_counts)
            
            # Step 6: Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            stats['processing_time_seconds'] = round(processing_time, 2)
            
            # Step 7: Insert metadata
            logger.info("Step 4: Recording metadata")
            insert_merge_metadata(conn, merge_date, stats)
            
            # Commit final transaction
            conn.commit()
            logger.info(f"Merge ETL completed in {processing_time:.2f} seconds")
            
            return {
                'status': 'success',
                'merge_date': str(merge_date),
                'statistics': stats
            }
    
    except Exception as e:
        logger.error(f"Merge ETL failed: {e}")
        raise Exception(f"Merge ETL error: {str(e)}")
