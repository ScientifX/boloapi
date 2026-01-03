import httpx
import json
import logging
import csv
import asyncio
import os
import re
import hashlib

from config import DB_CONFIG
from typing import Literal
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any
from io import StringIO
from contextlib import contextmanager 

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2.extensions import connection as Connection
from fastapi import APIRouter, HTTPException, status, Response, Request, Query, Depends
from pydantic import BaseModel, Field
from fastapi import APIRouter

# Import auth utilities
from auth import UserRole
from auth_jwt import require_jwt_role
from utils_array import extract_and_clean_array
from service_nottification import detect_all_changes, process_pending_notifications
from service_link_validation import (
    validate_links_from_file, 
    validate_links_from_file_web,
    get_link_check_summary, 
    get_failed_links,
    get_cache_stats,
    clear_cache,
    download_files_for_archive,
    create_documents_archive,
    get_archive_info
)

# Response Models
class ImportSummary(BaseModel):
    """Summary of the import operation"""
    status: str
    total_records_in_file: int
    records_inserted: int
    records_skipped: int
    skipped_reasons: Dict[str, int] = Field(default_factory=dict)
    pull_date: str
    processing_time_seconds: float
    errors: List[str] = Field(default_factory=list)

class ImportRequest(BaseModel):
    """Request model for import endpoint"""
    file_path: str = Field(..., description="Absolute path to the JSON file on the server")
    pull_date: Optional[str] = Field(None, description="Date of the data pull (YYYY-MM-DD). Defaults to today.")

VOLATILE_HASH_FIELDS = {'modified', '@id'}
FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

def load_simple_fields_from_schema(schema_path: str) -> list[str]:
    """
    Extract simple field names from the FBI Wanted API schema in the order they appear.
    Simple fields are those with primitive types or arrays of primitives.
    """
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    
    # Get the WantedPerson definition
    bolo_person = schema['definitions']['WantedPerson']
    properties = bolo_person['properties']
    
    simple_fields = []
    
    # Iterate in order (Python 3.7+ dicts maintain insertion order)
    for field_name, field_spec in properties.items():
        if 'type' in field_spec:
            field_type = field_spec['type']
            
            # Handle union types like ["string", "null"]
            if isinstance(field_type, list):
                types = [t for t in field_type if t != 'null']
                if len(types) == 1:
                    field_type = types[0]
                else:
                    continue
            
            # Simple primitive types
            if field_type in ['string', 'integer', 'number', 'boolean']:
                simple_fields.append(field_name)
            
            # Arrays of primitives
            elif field_type == 'array':
                if 'items' in field_spec:
                    items_spec = field_spec['items']
                    
                    # Skip arrays of objects (with $ref)
                    if '$ref' in items_spec:
                        continue
                    
                    # Check if items has a simple type
                    if 'type' in items_spec:
                        item_type = items_spec['type']
                        if item_type in ['string', 'integer', 'number', 'boolean']:
                            simple_fields.append(field_name)
                        elif item_type == 'object':
                            continue
    
    return simple_fields

def convert_to_csv(data: dict, simple_fields: list[str]) -> str:
    """
    Convert FBI API JSON response to CSV format using only simple fields.
    Arrays are converted to semicolon-separated strings.
    """
    items = data.get('items', [])
    
    if not items:
        # Return empty CSV with headers
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=simple_fields)
        writer.writeheader()
        return output.getvalue()
    
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=simple_fields, extrasaction='ignore')
    writer.writeheader()
    
    for item in items:
        # Convert arrays to semicolon-separated strings
        row = {}
        for field in simple_fields:
            value = item.get(field)
            
            if value is None:
                row[field] = ''
            elif isinstance(value, list):
                # Join array elements with semicolons
                row[field] = '; '.join(str(v) for v in value)
            else:
                row[field] = value
        
        writer.writerow(row)
    
    return output.getvalue()

def parse_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse date string to datetime, handling various formats"""
    if not date_str:
        return None
    
    try:
        # Try ISO format with timezone
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        try:
            # Try without timezone
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return None

def compute_content_hash(full_data_clean: dict) -> str:
    """
    Compute SHA-256 hash of cleaned data, excluding volatile fields
    that may change without meaningful content updates.
    """
    # Create copy without volatile fields
    hashable_data = {k: v for k, v in full_data_clean.items() 
                     if k not in VOLATILE_HASH_FIELDS}
    
    # Stable JSON serialization with sorted keys
    json_str = json.dumps(hashable_data, sort_keys=True, default=str)
    
    return hashlib.sha256(json_str.encode('utf-8')).hexdigest()

def extract_array_field(data: Dict, field: str) -> Optional[List[str]]:
    """Extract array field with cleaning for PostgreSQL."""
    return extract_and_clean_array(data, field)

def extract_poster_url(images: List[Dict]) -> Optional[str]:
    """Extract the first original image URL as the poster URL"""
    if images and len(images) > 0:
        return images[0].get('original')
    return None

def clean_json_recursive(data: Any, field_name: str = '') -> Any:
    """
    Recursively clean JSON data by:
    - Trimming whitespace from all string values
    - Removing control characters from strings (replacing adjacent ones with single space)
    - Removing basic HTML tags and decoding HTML entities
    - Normalizing email addresses (lowercase, trimmed)
    - Smart title case for 'title' field
    - Normalizing punctuation (quotes, dashes)
    - Removing zero-width and special Unicode characters
    - Fixing repeated words
    - Converting empty strings to null
    - Preserving structure and null values
    - Processing nested objects and arrays
    """
    import html
    
    # Control characters pattern (exclude space)
    control_chars = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]+')
    
    # HTML tags pattern
    html_tags = re.compile(r'</?(?:p|br|b|i|u|strong|em|span|div)(?:\s[^>]*)?>|Ã‚', re.IGNORECASE)
    
    # Email pattern
    email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    
    # Zero-width and invisible characters
    invisible_chars = re.compile(r'[\u200B-\u200D\uFEFF\u00AD]')
    
    # BOM and directional markers
    special_unicode = re.compile(r'[\uFEFF\u200E\u200F\u202A-\u202E]')
    
    # Various quote marks to normalize
    quote_map = {
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201A': "'",  # Single low-9 quotation mark
        '\u201B': "'",  # Single high-reversed-9 quotation mark
        '\u201C': '"',  # Left double quotation mark
        '\u201D': '"',  # Right double quotation mark
        '\u201E': '"',  # Double low-9 quotation mark
        '\u201F': '"',  # Double high-reversed-9 quotation mark
        '\u2032': "'",  # Prime
        '\u2033': '"',  # Double prime
        '\u0060': "'",  # Grave accent
        '\u00B4': "'",  # Acute accent
    }
    
    # Various dash characters to normalize to hyphen
    dash_map = {
        '\u2010': '-',  # Hyphen
        '\u2011': '-',  # Non-breaking hyphen
        '\u2012': '-',  # Figure dash
        '\u2013': '-',  # En dash
        '\u2014': '-',  # Em dash
        '\u2015': '-',  # Horizontal bar
    }
    
    # Words to keep lowercase in title case (articles, conjunctions, prepositions)
    lowercase_words = {
        'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'in', 
        'into', 'nor', 'of', 'on', 'or', 'over', 'the', 'to', 'under', 
        'with', 'via', 'per', 'vs'
    }
    
    # Common acronyms to preserve (without periods)
    acronyms = {
        'fbi', 'cia', 'atm', 'usa', 'uk', 'un', 'nato', 'aids', 'hiv', 
        'dna', 'rna', 'ceo', 'cfo', 'cto', 'phd', 'md', 'jr', 'sr', 'iv',
        'us', 'eu', 'nasa', 'swat', 'dea', 'atf', 'nsa', 'dhs'
    }
    
    # Pattern for abbreviations with periods (U.S., U.K., etc.)
    abbreviation_pattern = re.compile(r'^[A-Z](\.[A-Z])+\.?$')
    
    # Roman numerals
    roman_numerals = re.compile(r'^(i|ii|iii|iv|v|vi|vii|viii|ix|x|xi|xii|xiii|xiv|xv)$', re.IGNORECASE)
    
    def smart_title_case(text: str) -> str:
        """
        Apply smart title case with proper handling of:
        - Acronyms (FBI, USA, etc.)
        - Abbreviations with periods (U.S., U.K., Jr., Sr., etc.)
        - Roman numerals (I, II, III, etc.)
        - Small words (and, or, the, of, etc.)
        - Name prefixes (Mc, Mac, O', De, Van, etc.)
        - First and last words always capitalized
        """
        words = text.split()
        if not words:
            return text
        
        result = []
        for i, word in enumerate(words):
            # Preserve punctuation
            leading_punct = ''
            trailing_punct = ''
            
            # Extract leading punctuation
            while word and not word[0].isalnum():
                leading_punct += word[0]
                word = word[1:]
            
            # Extract trailing punctuation (but not periods that are part of abbreviations)
            if abbreviation_pattern.match(word):
                # This is an abbreviation like U.S. or Jr. - don't strip the periods
                result.append(leading_punct + word.upper())
                continue
            
            # Extract trailing punctuation for normal words
            while word and not word[-1].isalnum():
                trailing_punct = word[-1] + trailing_punct
                word = word[:-1]
            
            if not word:
                result.append(leading_punct + trailing_punct)
                continue
            
            word_lower = word.lower()
            
            # Check if it's an abbreviation with periods (after removing trailing punct)
            if abbreviation_pattern.match(word):
                result.append(leading_punct + word.upper() + trailing_punct)
                continue
            
            # Check if it's an acronym
            if word_lower in acronyms:
                # Special handling for Jr. and Sr.
                if word_lower in ['jr', 'sr']:
                    result.append(leading_punct + word.capitalize() + '.' + trailing_punct)
                else:
                    result.append(leading_punct + word_lower.upper() + trailing_punct)
                continue
            
            # Check if it's a Roman numeral
            if roman_numerals.match(word_lower):
                result.append(leading_punct + word_lower.upper() + trailing_punct)
                continue
            
            # First or last word - always capitalize
            if i == 0 or i == len(words) - 1:
                # Handle special name prefixes
                if word_lower.startswith("mc") and len(word) > 2:
                    result.append(leading_punct + "Mc" + word[2].upper() + word[3:].lower() + trailing_punct)
                elif word_lower.startswith("mac") and len(word) > 3:
                    result.append(leading_punct + "Mac" + word[3].upper() + word[4:].lower() + trailing_punct)
                elif word_lower.startswith("o'") and len(word) > 2:
                    result.append(leading_punct + "O'" + word[2].upper() + word[3:].lower() + trailing_punct)
                else:
                    result.append(leading_punct + word.capitalize() + trailing_punct)
                continue
            
            # Small words stay lowercase (unless first/last)
            if word_lower in lowercase_words:
                result.append(leading_punct + word_lower + trailing_punct)
                continue
            
            # Handle special name prefixes
            if word_lower.startswith("mc") and len(word) > 2:
                result.append(leading_punct + "Mc" + word[2].upper() + word[3:].lower() + trailing_punct)
            elif word_lower.startswith("mac") and len(word) > 3:
                result.append(leading_punct + "Mac" + word[3].upper() + word[4:].lower() + trailing_punct)
            elif word_lower.startswith("o'") and len(word) > 2:
                result.append(leading_punct + "O'" + word[2].upper() + word[3:].lower() + trailing_punct)
            elif word_lower in ['de', 'van', 'von', 'der', 'den', 'del', 'della', 'di', 'da', 'le', 'la']:
                result.append(leading_punct + word_lower + trailing_punct)
            else:
                result.append(leading_punct + word.capitalize() + trailing_punct)
        
        return ' '.join(result)
    
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            cleaned[key] = clean_json_recursive(value, field_name=key)
        return cleaned
    
    elif isinstance(data, list):
        return [clean_json_recursive(item, field_name=field_name) for item in data]
    
    elif isinstance(data, str):
        # Decode HTML entities first
        decoded = html.unescape(data)
        
        # Remove HTML tags
        no_html = html_tags.sub('', decoded)
        
        # Remove BOM and directional markers
        no_special = special_unicode.sub('', no_html)
        
        # Remove zero-width and invisible characters
        no_invisible = invisible_chars.sub('', no_special)
        
        # Normalize quotes
        for old_quote, new_quote in quote_map.items():
            no_invisible = no_invisible.replace(old_quote, new_quote)
            # Remove remaining double quotes from array elements
            no_invisible = no_invisible.replace('"', '')
        
        # Normalize dashes
        for old_dash, new_dash in dash_map.items():
            no_invisible = no_invisible.replace(old_dash, new_dash)
        
        # Replace control characters with space
        no_control = control_chars.sub(' ', no_invisible)
        
        # Collapse multiple spaces and trim
        trimmed = re.sub(r'\s+', ' ', no_control).strip()
        
        # Fix repeated words (simple case)
        trimmed = re.sub(r'\b(\w+)\s+\1\b', r'\1', trimmed, flags=re.IGNORECASE)
        
        # Remove excessive punctuation (more than 3 of the same)
        trimmed = re.sub(r'([!?.]){4,}', r'\1\1\1', trimmed)
        
        # Convert empty strings to null
        if trimmed == '':
            return None
        
        # Email normalization - if string matches email pattern
        if email_pattern.fullmatch(trimmed):
            # Convert to lowercase and strip whitespace
            trimmed = trimmed.lower().strip()
            # Remove dots before @ for Gmail (optional - uncomment if desired)
            # if '@gmail.com' in trimmed:
            #     local, domain = trimmed.split('@')
            #     local = local.replace('.', '')
            #     trimmed = f"{local}@{domain}"
        
        # Apply smart title case only for 'title' field
        if field_name == 'title' and trimmed.isupper():
            trimmed = smart_title_case(trimmed)
        
        return trimmed
    
    else:
        # Return other types unchanged (int, float, bool, None)
        return data
    
def bolo_process(item: Dict, pull_date: date) -> Optional[Dict[str, Any]]:
    """
    Process a single wanted person record into database-ready format.
    Now includes content_hash computation for version tracking.
    
    Returns None if the record should be skipped (missing uid).
    """
    from router_etl import (
        extract_array_field, extract_poster_url, parse_date, clean_json_recursive
    )
    
    uid = item.get('uid')
    if not uid:
        return None

    # Create cleaned version of full_data
    full_data_clean = clean_json_recursive(item)
    
    # Compute content hash for version tracking
    content_hash = compute_content_hash(full_data_clean)

    return {
        'age_max': item.get('age_max'),
        'age_min': item.get('age_min'),
        'aliases': extract_array_field(item, 'aliases'),
        'build': item.get('build'),
        'caution': item.get('caution'),
        'complexion': item.get('complexion'),
        'content_hash': content_hash,  # NEW
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


def bolo_process_web(item: Dict, pull_date: date) -> Optional[Dict[str, Any]]:
    """
    Process a single web-scraped wanted person record into database-ready format.
    Now includes content_hash computation and related_cases field.
    
    Returns None if the record should be skipped (missing uid).
    """
    from router_etl import (
        extract_array_field, extract_poster_url, parse_date, clean_json_recursive
    )
    
    uid = item.get('uid')
    if not uid:
        return None

    # Create cleaned version of full_data
    full_data_clean = clean_json_recursive(item)
    
    # Compute content hash for version tracking
    content_hash = compute_content_hash(full_data_clean)

    return {
        'age_max': item.get('age_max'),
        'age_min': item.get('age_min'),
        'aliases': extract_array_field(item, 'aliases'),
        'build': item.get('build'),
        'caution': item.get('caution'),
        'complexion': item.get('complexion'),
        'content_hash': content_hash,  # NEW
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
        'related_cases': extract_array_field(item, 'related_cases'),
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


def bolo_insert(conn: Connection, records: List[Dict[str, Any]], pull_date: date) -> Dict[str, Any]:
    """
    Insert/update wanted persons records using hash-based versioning.
    
    Primary key: (uid, content_hash)
    
    Logic for each record:
    1. If (uid, content_hash) exists: Just update last_seen_date (content unchanged)
    2. If hash is new for this uid:
       a. Close current version (set valid_to)
       b. Insert new version with incremented version_number
       c. Set change_type = NEW (if first version) or MODIFIED (if subsequent)
    3. Track if uid was previously REMOVED and is now returning (change_type = RETURNED)
    
    Returns:
        Dict with counts: {
            "inserted": int,      # New content versions inserted
            "updated": int,       # Existing versions touched (last_seen_date only)
            "skipped": int,       # Records skipped (shouldn't happen normally)
            "new_uids": list,     # UIDs that are completely new
            "modified_uids": list # UIDs with content changes
        }
    """
    if not records:
        return {"inserted": 0, "updated": 0, "skipped": 0, "new_uids": [], "modified_uids": []}

    inserted_count = 0
    updated_count = 0
    new_uids = []
    modified_uids = []
    returned_uids = []
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for record in records:
            uid = record['uid']
            content_hash = record['content_hash']
            
            # Check if this exact content already exists
            cur.execute("""
                SELECT uid, content_hash, version_number, valid_to, change_type
                FROM tbl_bolo 
                WHERE uid = %s AND content_hash = %s
            """, (uid, content_hash))
            existing = cur.fetchone()
            
            if existing:
                # Content unchanged - just update last_seen_date
                cur.execute("""
                    UPDATE tbl_bolo 
                    SET last_seen_date = %s, updated_at = NOW()
                    WHERE uid = %s AND content_hash = %s
                """, (pull_date, uid, content_hash))
                updated_count += 1
                logger.debug(f"Updated last_seen_date for {uid} (content unchanged)")
            else:
                # New content for this uid - need to create new version
                
                # Get current version info for this uid
                cur.execute("""
                    SELECT uid, content_hash, version_number, change_type
                    FROM tbl_bolo 
                    WHERE uid = %s AND valid_to IS NULL
                    ORDER BY version_number DESC
                    LIMIT 1
                """, (uid,))
                current_version = cur.fetchone()
                
                # Check if this uid was previously removed (for RETURNED detection)
                cur.execute("""
                    SELECT 1 FROM tbl_bolo 
                    WHERE uid = %s AND change_type = 'REMOVED'
                    LIMIT 1
                """, (uid,))
                was_removed = cur.fetchone() is not None
                
                if current_version:
                    # Close current version
                    cur.execute("""
                        UPDATE tbl_bolo 
                        SET valid_to = %s, 
                            is_active = FALSE,
                            updated_at = NOW()
                        WHERE uid = %s AND content_hash = %s
                    """, (pull_date, uid, current_version['content_hash']))
                    
                    new_version_number = current_version['version_number'] + 1
                    
                    # Determine change type
                    if was_removed:
                        change_type = 'RETURNED'
                        returned_uids.append(uid)
                    else:
                        change_type = 'MODIFIED'
                        modified_uids.append(uid)
                else:
                    # First version for this uid
                    new_version_number = 1
                    change_type = 'NEW'
                    new_uids.append(uid)
                
                # Insert new version
                cur.execute("""
                    INSERT INTO tbl_bolo (
                        uid, content_hash, version_number, valid_from, valid_to,
                        change_type, is_active, first_seen_date, last_seen_date, data_pull_date,
                        age_max, age_min, aliases, build, caution, complexion,
                        coordinates, dates_of_birth_used, description, details,
                        eyes, eyes_raw, field_offices, full_data, full_data_clean,
                        hair, hair_raw, height_max, height_min, languages,
                        legat_names, locations, modified, nationality, ncic,
                        occupations, path, pathid, person_classification,
                        place_of_birth, possible_countries, possible_states,
                        poster_classification, poster_url, publication, race, race_raw,
                        remarks, reward_max, reward_min, reward_text,
                        scars_and_marks, sex, status, subjects, suspects,
                        title, url, warning_message, weight, weight_max, weight_min
                    ) VALUES (
                        %s, %s, %s, %s, NULL,
                        %s, TRUE, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                """, (
                    uid, content_hash, new_version_number, pull_date,
                    change_type, pull_date, pull_date, pull_date,
                    record.get('age_max'), record.get('age_min'), record.get('aliases'),
                    record.get('build'), record.get('caution'), record.get('complexion'),
                    record.get('coordinates'), record.get('dates_of_birth_used'),
                    record.get('description'), record.get('details'),
                    record.get('eyes'), record.get('eyes_raw'), record.get('field_offices'),
                    record.get('full_data'), record.get('full_data_clean'),
                    record.get('hair'), record.get('hair_raw'),
                    record.get('height_max'), record.get('height_min'),
                    record.get('languages'), record.get('legat_names'),
                    record.get('locations'), record.get('modified'),
                    record.get('nationality'), record.get('ncic'),
                    record.get('occupations'), record.get('path'), record.get('pathid'),
                    record.get('person_classification'), record.get('place_of_birth'),
                    record.get('possible_countries'), record.get('possible_states'),
                    record.get('poster_classification'), record.get('poster_url'),
                    record.get('publication'), record.get('race'), record.get('race_raw'),
                    record.get('remarks'), record.get('reward_max'),
                    record.get('reward_min'), record.get('reward_text'),
                    record.get('scars_and_marks'), record.get('sex'),
                    record.get('status'), record.get('subjects'), record.get('suspects'),
                    record.get('title'), record.get('url'),
                    record.get('warning_message'), record.get('weight'),
                    record.get('weight_max'), record.get('weight_min')
                ))
                
                inserted_count += 1
                logger.debug(f"Inserted version {new_version_number} for {uid} ({change_type})")
    
    logger.info(f"UPSERT complete: {inserted_count} inserted, {updated_count} updated, "
                f"{len(new_uids)} new UIDs, {len(modified_uids)} modified, {len(returned_uids)} returned")
    
    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "skipped": 0,
        "new_uids": new_uids,
        "modified_uids": modified_uids,
        "returned_uids": returned_uids
    }


def bolo_insert_web(conn: Connection, records: List[Dict[str, Any]], pull_date: date) -> Dict[str, Any]:
    """
    Insert/update web-scraped wanted persons records using hash-based versioning.
    
    Same logic as bolo_insert() but for tbl_bolo_web.
    Includes related_cases field.
    """
    if not records:
        return {"inserted": 0, "updated": 0, "skipped": 0, "new_uids": [], "modified_uids": []}

    inserted_count = 0
    updated_count = 0
    new_uids = []
    modified_uids = []
    returned_uids = []
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        for record in records:
            uid = record['uid']
            content_hash = record['content_hash']
            
            # Check if this exact content already exists
            cur.execute("""
                SELECT uid, content_hash, version_number, valid_to, change_type
                FROM tbl_bolo_web 
                WHERE uid = %s AND content_hash = %s
            """, (uid, content_hash))
            existing = cur.fetchone()
            
            if existing:
                # Content unchanged - just update last_seen_date
                cur.execute("""
                    UPDATE tbl_bolo_web 
                    SET last_seen_date = %s, updated_at = NOW()
                    WHERE uid = %s AND content_hash = %s
                """, (pull_date, uid, content_hash))
                updated_count += 1
            else:
                # New content for this uid - need to create new version
                
                # Get current version info for this uid
                cur.execute("""
                    SELECT uid, content_hash, version_number, change_type
                    FROM tbl_bolo_web 
                    WHERE uid = %s AND valid_to IS NULL
                    ORDER BY version_number DESC
                    LIMIT 1
                """, (uid,))
                current_version = cur.fetchone()
                
                # Check if this uid was previously removed
                cur.execute("""
                    SELECT 1 FROM tbl_bolo_web 
                    WHERE uid = %s AND change_type = 'REMOVED'
                    LIMIT 1
                """, (uid,))
                was_removed = cur.fetchone() is not None
                
                if current_version:
                    # Close current version
                    cur.execute("""
                        UPDATE tbl_bolo_web 
                        SET valid_to = %s, 
                            is_active = FALSE,
                            updated_at = NOW()
                        WHERE uid = %s AND content_hash = %s
                    """, (pull_date, uid, current_version['content_hash']))
                    
                    new_version_number = current_version['version_number'] + 1
                    
                    if was_removed:
                        change_type = 'RETURNED'
                        returned_uids.append(uid)
                    else:
                        change_type = 'MODIFIED'
                        modified_uids.append(uid)
                else:
                    new_version_number = 1
                    change_type = 'NEW'
                    new_uids.append(uid)
                
                # Insert new version (includes related_cases)
                cur.execute("""
                    INSERT INTO tbl_bolo_web (
                        uid, content_hash, version_number, valid_from, valid_to,
                        change_type, is_active, first_seen_date, last_seen_date, data_pull_date,
                        age_max, age_min, aliases, build, caution, complexion,
                        coordinates, dates_of_birth_used, description, details,
                        eyes, eyes_raw, field_offices, full_data, full_data_clean,
                        hair, hair_raw, height_max, height_min, languages,
                        legat_names, locations, modified, nationality, ncic,
                        occupations, path, pathid, person_classification,
                        place_of_birth, possible_countries, possible_states,
                        poster_classification, poster_url, publication, race, race_raw,
                        related_cases, remarks, reward_max, reward_min, reward_text,
                        scars_and_marks, sex, status, subjects, suspects,
                        title, url, warning_message, weight, weight_max, weight_min
                    ) VALUES (
                        %s, %s, %s, %s, NULL,
                        %s, TRUE, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                """, (
                    uid, content_hash, new_version_number, pull_date,
                    change_type, pull_date, pull_date, pull_date,
                    record.get('age_max'), record.get('age_min'), record.get('aliases'),
                    record.get('build'), record.get('caution'), record.get('complexion'),
                    record.get('coordinates'), record.get('dates_of_birth_used'),
                    record.get('description'), record.get('details'),
                    record.get('eyes'), record.get('eyes_raw'), record.get('field_offices'),
                    record.get('full_data'), record.get('full_data_clean'),
                    record.get('hair'), record.get('hair_raw'),
                    record.get('height_max'), record.get('height_min'),
                    record.get('languages'), record.get('legat_names'),
                    record.get('locations'), record.get('modified'),
                    record.get('nationality'), record.get('ncic'),
                    record.get('occupations'), record.get('path'), record.get('pathid'),
                    record.get('person_classification'), record.get('place_of_birth'),
                    record.get('possible_countries'), record.get('possible_states'),
                    record.get('poster_classification'), record.get('poster_url'),
                    record.get('publication'), record.get('race'), record.get('race_raw'),
                    record.get('related_cases'), record.get('remarks'),
                    record.get('reward_max'), record.get('reward_min'),
                    record.get('reward_text'), record.get('scars_and_marks'),
                    record.get('sex'), record.get('status'),
                    record.get('subjects'), record.get('suspects'),
                    record.get('title'), record.get('url'),
                    record.get('warning_message'), record.get('weight'),
                    record.get('weight_max'), record.get('weight_min')
                ))
                
                inserted_count += 1
    
    logger.info(f"Web UPSERT complete: {inserted_count} inserted, {updated_count} updated")
    
    return {
        "inserted": inserted_count,
        "updated": updated_count,
        "skipped": 0,
        "new_uids": new_uids,
        "modified_uids": modified_uids,
        "returned_uids": returned_uids
    }


def update_active_status(conn: Connection) -> Dict[str, int]:
    """
    Ensure is_active flags are consistent with valid_to.
    
    With hash-based versioning, is_active should be:
    - TRUE only for records where valid_to IS NULL AND change_type != 'REMOVED'
    - FALSE for all other records
    
    This is mostly a consistency check since the insert/update logic
    should handle this correctly.
    """
    with conn.cursor() as cur:
        # Set FALSE where it should be FALSE
        cur.execute("""
            UPDATE tbl_bolo
            SET is_active = FALSE,
                updated_at = NOW()
            WHERE is_active = TRUE
              AND (valid_to IS NOT NULL OR change_type = 'REMOVED')
        """)
        rows_deactivated = cur.rowcount
        
        # Set TRUE where it should be TRUE
        cur.execute("""
            UPDATE tbl_bolo
            SET is_active = TRUE,
                updated_at = NOW()
            WHERE is_active = FALSE
              AND valid_to IS NULL
              AND change_type != 'REMOVED'
        """)
        rows_activated = cur.rowcount
        
        logger.info(f"Active status sync: {rows_deactivated} deactivated, {rows_activated} activated")
        
        return {
            "deactivated": rows_deactivated,
            "activated": rows_activated
        }


def update_active_status_web(conn: Connection) -> Dict[str, int]:
    """
    Ensure is_active flags are consistent with valid_to for tbl_bolo_web.
    Same logic as update_active_status().
    """
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE tbl_bolo_web
            SET is_active = FALSE,
                updated_at = NOW()
            WHERE is_active = TRUE
              AND (valid_to IS NOT NULL OR change_type = 'REMOVED')
        """)
        rows_deactivated = cur.rowcount
        
        cur.execute("""
            UPDATE tbl_bolo_web
            SET is_active = TRUE,
                updated_at = NOW()
            WHERE is_active = FALSE
              AND valid_to IS NULL
              AND change_type != 'REMOVED'
        """)
        rows_activated = cur.rowcount
        
        logger.info(f"Web active status sync: {rows_deactivated} deactivated, {rows_activated} activated")
        
        return {
            "deactivated": rows_deactivated,
            "activated": rows_activated
        }


def insert_api_metadata(
    conn: Connection, 
    total: int, 
    page: int, 
    pull_date: date,
    etl_stats: Optional[Dict[str, Any]] = None
    ):
    """
    Insert or update API pull metadata with ETL statistics.
    
    Args:
        conn: Database connection
        total: Total records reported by FBI API
        page: Page number from API response
        pull_date: Date of the data pull
        etl_stats: Optional dict containing:
            - records_inserted: Number of new records inserted
            - records_updated: Number of existing records updated
            - records_skipped: Number of records skipped
            - active_count: Total active records after pull
            - inactive_count: Total inactive records after pull
            - processing_time_seconds: Total processing time
    """
    with conn.cursor() as cur:
        if etl_stats:
            # Full insert/update with ETL statistics
            cur.execute("""
                INSERT INTO tbl_bolo_control (
                    pull_date, 
                    total_records, 
                    page, 
                    pull_timestamp,
                    records_inserted,
                    records_updated,
                    records_skipped,
                    active_count,
                    inactive_count,
                    processing_time_seconds
                )
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pull_date) 
                DO UPDATE SET 
                    total_records = EXCLUDED.total_records,
                    page = EXCLUDED.page,
                    pull_timestamp = NOW(),
                    records_inserted = EXCLUDED.records_inserted,
                    records_updated = EXCLUDED.records_updated,
                    records_skipped = EXCLUDED.records_skipped,
                    active_count = EXCLUDED.active_count,
                    inactive_count = EXCLUDED.inactive_count,
                    processing_time_seconds = EXCLUDED.processing_time_seconds
            """, (
                pull_date, 
                total, 
                page,
                etl_stats.get('records_inserted', 0),
                etl_stats.get('records_updated', 0),
                etl_stats.get('records_skipped', 0),
                etl_stats.get('active_count', 0),
                etl_stats.get('inactive_count', 0),
                etl_stats.get('processing_time_seconds', 0)
            ))
            logger.info(f"Metadata updated with ETL stats for pull_date={pull_date}")
        else:
            # Basic insert (for backward compatibility)
            cur.execute("""
                INSERT INTO tbl_bolo_control (pull_date, total_records, page, pull_timestamp)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (pull_date) 
                DO UPDATE SET 
                    total_records = EXCLUDED.total_records,
                    page = EXCLUDED.page,
                    pull_timestamp = NOW()
            """, (pull_date, total, page))
            logger.info(f"Basic metadata inserted for pull_date={pull_date}")


def insert_api_metadata_web(
    conn: Connection, 
    total: int, 
    page: int, 
    pull_date: date,
    etl_stats: Optional[Dict[str, Any]] = None
):
    """
    Insert or update web scrape metadata with ETL statistics.
    
    Args:
        conn: Database connection
        total: Total records reported in web scrape
        page: Page number from scrape response
        pull_date: Date of the data pull
        etl_stats: Optional dict containing ETL statistics
    """
    with conn.cursor() as cur:
        if etl_stats:
            # Full insert/update with ETL statistics
            cur.execute("""
                INSERT INTO tbl_bolo_control_web (
                    pull_date, 
                    total_records, 
                    page, 
                    pull_timestamp,
                    records_inserted,
                    records_updated,
                    records_skipped,
                    active_count,
                    inactive_count,
                    processing_time_seconds
                )
                VALUES (%s, %s, %s, NOW(), %s, %s, %s, %s, %s, %s)
                ON CONFLICT (pull_date) 
                DO UPDATE SET 
                    total_records = EXCLUDED.total_records,
                    page = EXCLUDED.page,
                    pull_timestamp = NOW(),
                    records_inserted = EXCLUDED.records_inserted,
                    records_updated = EXCLUDED.records_updated,
                    records_skipped = EXCLUDED.records_skipped,
                    active_count = EXCLUDED.active_count,
                    inactive_count = EXCLUDED.inactive_count,
                    processing_time_seconds = EXCLUDED.processing_time_seconds
            """, (
                pull_date, 
                total, 
                page,
                etl_stats.get('records_inserted', 0),
                etl_stats.get('records_updated', 0),
                etl_stats.get('records_skipped', 0),
                etl_stats.get('active_count', 0),
                etl_stats.get('inactive_count', 0),
                etl_stats.get('processing_time_seconds', 0)
            ))
            logger.info(f"Web metadata updated with ETL stats for pull_date={pull_date}")
        else:
            # Basic insert (for backward compatibility)
            cur.execute("""
                INSERT INTO tbl_bolo_control_web (pull_date, total_records, page, pull_timestamp)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (pull_date) 
                DO UPDATE SET 
                    total_records = EXCLUDED.total_records,
                    page = EXCLUDED.page,
                    pull_timestamp = NOW()
            """, (pull_date, total, page))
            logger.info(f"Basic web metadata inserted for pull_date={pull_date}")


def update_record_status(conn: Connection, current_uids: List[str], pull_date: date):
    """
    Mark records as inactive if they're not in the current pull
    Updates last_seen_date for active records
    """
    with conn.cursor() as cur:
        # Update last_seen_date for records in current pull
        if current_uids:
            cur.execute("""
                UPDATE tbl_bolo
                SET last_seen_date = %s,
                    updated_at = NOW()
                WHERE uid = ANY(%s)
                  AND is_active = true
                  AND last_seen_date < %s
            """, (pull_date, current_uids, pull_date))
        
    with conn.cursor() as cur:
        cur.execute("CALL sp_clean_text()")
        cur.execute("CALL sp_clean_array()")
        cur.execute("CALL sp_clean_jsonb()")
        cur.execute("CALL sp_prune()")


def mark_missing_uids_inactive(conn: Connection, current_uids: List[str], pull_date: date) -> Dict[str, Any]:
    """
    Mark UIDs not in current pull as REMOVED by inserting tombstone records.
    
    For each uid that was active but is now missing:
    1. Close the current version (set valid_to, is_active = FALSE)
    2. Insert a new REMOVED tombstone version
    
    Args:
        conn: Database connection
        current_uids: List of UIDs present in today's pull
        pull_date: Current pull date
        
    Returns:
        Dict with counts and lists of removed UIDs
    """
    if not current_uids:
        logger.warning("No current UIDs provided - skipping mark_missing_uids_inactive")
        return {"marked_inactive": 0, "removed_uids": []}
    
    removed_uids = []
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # Find UIDs that are currently active but not in current pull
        cur.execute("""
            SELECT DISTINCT uid, content_hash, version_number, title, full_data, full_data_clean
            FROM tbl_bolo 
            WHERE valid_to IS NULL 
              AND is_active = TRUE
              AND change_type != 'REMOVED'
              AND uid NOT IN (SELECT UNNEST(%s::text[]))
        """, (current_uids,))
        
        missing_records = cur.fetchall()
        
        for record in missing_records:
            uid = record['uid']
            current_hash = record['content_hash']
            current_version = record['version_number']
            
            # Close current version
            cur.execute("""
                UPDATE tbl_bolo 
                SET valid_to = %s, 
                    is_active = FALSE,
                    became_inactive_at = NOW(),
                    updated_at = NOW()
                WHERE uid = %s AND content_hash = %s
            """, (pull_date, uid, current_hash))
            
            # Generate a unique hash for the tombstone (based on removal date)
            tombstone_data = {
                'uid': uid,
                'removed_date': str(pull_date),
                'previous_version': current_version
            }
            tombstone_hash = hashlib.sha256(
                json.dumps(tombstone_data, sort_keys=True).encode('utf-8')
            ).hexdigest()
            
            # Handle JSONB fields - ensure they're JSON strings for insertion
            full_data_str = json.dumps(record['full_data']) if isinstance(record['full_data'], dict) else record['full_data']
            full_data_clean_str = json.dumps(record['full_data_clean']) if isinstance(record['full_data_clean'], dict) else record['full_data_clean']
            
            # Insert REMOVED tombstone
            cur.execute("""
                INSERT INTO tbl_bolo (
                    uid, content_hash, version_number, valid_from, valid_to,
                    change_type, is_active, first_seen_date, last_seen_date, data_pull_date,
                    title, full_data, full_data_clean, became_inactive_at
                ) VALUES (
                    %s, %s, %s, %s, NULL,
                    'REMOVED', FALSE, %s, %s, %s,
                    %s, %s, %s, NOW()
                )
                ON CONFLICT (uid, content_hash) DO NOTHING
            """, (
                uid, tombstone_hash, current_version + 1, pull_date,
                pull_date, pull_date, pull_date,
                record['title'], full_data_str, full_data_clean_str
            ))
            
            removed_uids.append(uid)
            logger.info(f"Marked {uid} as REMOVED (was version {current_version})")
    
    logger.info(f"Marked {len(removed_uids)} UIDs as REMOVED from wanted list")
    
    return {
        "marked_inactive": len(removed_uids),
        "removed_uids": removed_uids
    }


def mark_missing_uids_inactive_web(conn: Connection, current_uids: List[str], pull_date: date) -> Dict[str, Any]:
    """
    Mark UIDs not in current web pull as REMOVED by inserting tombstone records.
    Same logic as mark_missing_uids_inactive() but for tbl_bolo_web.
    """
    if not current_uids:
        logger.warning("Web: No current UIDs provided - skipping mark_missing_uids_inactive_web")
        return {"marked_inactive": 0, "removed_uids": []}
    
    removed_uids = []
    
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute("""
            SELECT DISTINCT uid, content_hash, version_number, title, full_data, full_data_clean
            FROM tbl_bolo_web 
            WHERE valid_to IS NULL 
              AND is_active = TRUE
              AND change_type != 'REMOVED'
              AND uid NOT IN (SELECT UNNEST(%s::text[]))
        """, (current_uids,))
        
        missing_records = cur.fetchall()
        
        for record in missing_records:
            uid = record['uid']
            current_hash = record['content_hash']
            current_version = record['version_number']
            
            cur.execute("""
                UPDATE tbl_bolo_web 
                SET valid_to = %s, 
                    is_active = FALSE,
                    became_inactive_at = NOW(),
                    updated_at = NOW()
                WHERE uid = %s AND content_hash = %s
            """, (pull_date, uid, current_hash))
            
            tombstone_data = {
                'uid': uid,
                'removed_date': str(pull_date),
                'previous_version': current_version
            }
            tombstone_hash = hashlib.sha256(
                json.dumps(tombstone_data, sort_keys=True).encode('utf-8')
            ).hexdigest()
            
            # Handle JSONB fields - ensure they're JSON strings for insertion
            full_data_str = json.dumps(record['full_data']) if isinstance(record['full_data'], dict) else record['full_data']
            full_data_clean_str = json.dumps(record['full_data_clean']) if isinstance(record['full_data_clean'], dict) else record['full_data_clean']
            
            cur.execute("""
                INSERT INTO tbl_bolo_web (
                    uid, content_hash, version_number, valid_from, valid_to,
                    change_type, is_active, first_seen_date, last_seen_date, data_pull_date,
                    title, full_data, full_data_clean, became_inactive_at
                ) VALUES (
                    %s, %s, %s, %s, NULL,
                    'REMOVED', FALSE, %s, %s, %s,
                    %s, %s, %s, NOW()
                )
                ON CONFLICT (uid, content_hash) DO NOTHING
            """, (
                uid, tombstone_hash, current_version + 1, pull_date,
                pull_date, pull_date, pull_date,
                record['title'], full_data_str, full_data_clean_str
            ))
            
            removed_uids.append(uid)
    
    logger.info(f"Web: Marked {len(removed_uids)} UIDs as REMOVED")
    
    return {
        "marked_inactive": len(removed_uids),
        "removed_uids": removed_uids
    }

def import_data_set(file_path: str, pull_date: date) -> ImportSummary:
    """
    Main import function - reads JSON file and imports to database with new merge logic.
    Now captures comprehensive ETL statistics in tbl_bolo_control.
    
    New flow:
    1. Process records from FBI API
    2. UPSERT records (insert new versions, update last_seen_date for existing)
    3. Update is_active flags (TRUE for max(modified) per uid, FALSE for others)
    4. Mark UIDs not in current pull as inactive
    5. Run cleanup procedures
    6. Capture final statistics and update metadata
    """
    start_time = datetime.now()
    
    # Read and parse JSON file
    try:
        json_path = Path(file_path)
        if not json_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON file: {str(e)}")
    except Exception as e:
        raise Exception(f"Error reading file: {str(e)}")
    
    total = data.get('total', 0)
    page = data.get('page', 1)
    items = data.get('items', [])
    
    if not items:
        # Even for empty pulls, record metadata
        processing_time = (datetime.now() - start_time).total_seconds()
        
        try:
            with get_db_connection() as conn:
                # Get current counts
                counts = get_active_inactive_counts(conn)
                
                # Insert metadata with zero statistics
                etl_stats = {
                    'records_inserted': 0,
                    'records_updated': 0,
                    'records_skipped': 0,
                    'active_count': counts['active_count'],
                    'inactive_count': counts['inactive_count'],
                    'processing_time_seconds': round(processing_time, 2)
                }
                insert_api_metadata(conn, total, page, pull_date, etl_stats)
                conn.commit()
        except Exception as e:
            logger.error(f"Error recording metadata for empty pull: {str(e)}")
        
        return ImportSummary(
            status="success",
            total_records_in_file=0,
            records_inserted=0,
            records_skipped=0,
            pull_date=str(pull_date),
            processing_time_seconds=round(processing_time, 2)
        )
    
    # Process records
    processed_records = []
    skipped_count = 0
    skipped_reasons = {"missing_uid": 0}

    for item in items:
        processed = bolo_process(item, pull_date)
        if processed:
            processed_records.append(processed)
        else:
            skipped_count += 1
            skipped_reasons["missing_uid"] += 1

    # Database operations (atomic transaction)
    try:
        with get_db_connection() as conn:
            # Step 1: UPSERT wanted persons (new merge logic)
            upsert_results = bolo_insert(conn, processed_records, pull_date)
            logger.info(f"UPSERT results: {upsert_results}")
            
            # Step 2: Update is_active flags for all records
            active_results = update_active_status(conn)
            logger.info(f"Active status update: {active_results}")
            
            # Step 3: Mark UIDs not in current pull as inactive
            current_uids = [r['uid'] for r in processed_records]
            missing_results = mark_missing_uids_inactive(conn, current_uids, pull_date)
            logger.info(f"Missing UIDs marked inactive: {missing_results}")
            
            # Step 4: Run cleanup procedures
            with conn.cursor() as cur:
                cur.execute("CALL sp_clean_text()")
                cur.execute("CALL sp_clean_array()")
                cur.execute("CALL sp_clean_jsonb()")
                cur.execute("CALL sp_prune()")
            
            # Step 5: Get final active/inactive counts
            final_counts = get_active_inactive_counts(conn)
            logger.info(f"Final counts: {final_counts}")
            
            # Step 6: Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Step 7: Insert comprehensive metadata
            etl_stats = {
                'records_inserted': upsert_results['inserted'],
                'records_updated': upsert_results['updated'],
                'records_skipped': skipped_count,
                'active_count': final_counts['active_count'],
                'inactive_count': final_counts['inactive_count'],
                'processing_time_seconds': round(processing_time, 2)
            }
            insert_api_metadata(conn, total, page, pull_date, etl_stats)
            
            # Commit transaction
            conn.commit()
            logger.info("Transaction committed successfully with metadata")

            try:
                # Get list of UIDs that were inserted (new records)
                inserted_uids = []  # We'll need to track these in bolo_insert
                
                # Get list of UIDs that were marked inactive (removed from FBI list)
                removed_uids_list = []
                with conn.cursor() as cur:
                    cur.execute('''
                        SELECT uid FROM tbl_bolo 
                        WHERE became_inactive_at IS NOT NULL 
                        AND became_inactive_at >= NOW() - INTERVAL '1 minute'
                    ''')
                    removed_uids_list = [r[0] for r in cur.fetchall()]
                
                # Detect and log all changes
                change_results = detect_all_changes(
                    conn=conn,
                    processed_records=processed_records,
                    inserted_uids=inserted_uids,
                    removed_uids=removed_uids_list,
                    pull_date=pull_date
                )
                logger.info(f"Change detection results: {change_results}")
                
                conn.commit()
            except Exception as e:
                logger.error(f"Error during change detection: {str(e)}")
                # Don't fail the whole refresh for notification errors
            
    except Exception as e:
        logger.error(f"Database error during import: {str(e)}")
        raise Exception(f"Database error: {str(e)}")
    
    # Return enhanced summary
    return ImportSummary(
        status="success",
        total_records_in_file=len(items),
        records_inserted=upsert_results["inserted"],
        records_skipped=skipped_count,
        skipped_reasons=skipped_reasons,
        pull_date=str(pull_date),
        processing_time_seconds=round(processing_time, 2)
    )


def import_data_set_web(file_path: str, pull_date: date) -> ImportSummary:
    """
    Main import function for web-scraped data - reads JSON file and imports to tbl_bolo_web.
    
    Note: This function does NOT process notifications. Notifications are handled by
    the API refresh process to avoid duplicate notifications to users.
    
    Flow:
    1. Process records from web scrape
    2. UPSERT records (insert new versions, update last_seen_date for existing)
    3. Update is_active flags (TRUE for max(modified) per uid, FALSE for others)
    4. Mark UIDs not in current pull as inactive
    5. Run cleanup procedures
    6. Capture final statistics and update metadata
    """
    start_time = datetime.now()
    
    # Read and parse JSON file
    try:
        json_path = Path(file_path)
        if not json_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON file: {str(e)}")
    except Exception as e:
        raise Exception(f"Error reading file: {str(e)}")
    
    total = data.get('total', 0)
    page = data.get('page', 1)
    items = data.get('items', [])
    
    if not items:
        # Even for empty pulls, record metadata
        processing_time = (datetime.now() - start_time).total_seconds()
        
        try:
            with get_db_connection() as conn:
                # Get current counts
                counts = get_active_inactive_counts_web(conn)
                
                # Insert metadata with zero statistics
                etl_stats = {
                    'records_inserted': 0,
                    'records_updated': 0,
                    'records_skipped': 0,
                    'active_count': counts['active_count'],
                    'inactive_count': counts['inactive_count'],
                    'processing_time_seconds': round(processing_time, 2)
                }
                insert_api_metadata_web(conn, total, page, pull_date, etl_stats)
                conn.commit()
        except Exception as e:
            logger.error(f"Web: Error recording metadata for empty pull: {str(e)}")
        
        return ImportSummary(
            status="success",
            total_records_in_file=0,
            records_inserted=0,
            records_skipped=0,
            pull_date=str(pull_date),
            processing_time_seconds=round(processing_time, 2)
        )
    
    # Process records
    processed_records = []
    skipped_count = 0
    skipped_reasons = {"missing_uid": 0}

    for item in items:
        processed = bolo_process_web(item, pull_date)
        if processed:
            processed_records.append(processed)
        else:
            skipped_count += 1
            skipped_reasons["missing_uid"] += 1

    # Database operations (atomic transaction)
    try:
        with get_db_connection() as conn:
            # Step 1: UPSERT wanted persons (web data)
            upsert_results = bolo_insert_web(conn, processed_records, pull_date)
            logger.info(f"Web UPSERT results: {upsert_results}")
            
            # Step 2: Update is_active flags for all records
            active_results = update_active_status_web(conn)
            logger.info(f"Web active status update: {active_results}")
            
            # Step 3: Mark UIDs not in current pull as inactive
            current_uids = [r['uid'] for r in processed_records]
            missing_results = mark_missing_uids_inactive_web(conn, current_uids, pull_date)
            logger.info(f"Web missing UIDs marked inactive: {missing_results}")
            
            # Step 4: Run cleanup procedures (same as API data)
            with conn.cursor() as cur:
                cur.execute("CALL sp_clean_text()")
                cur.execute("CALL sp_clean_array()")
                cur.execute("CALL sp_clean_jsonb()")
                cur.execute("CALL sp_prune()")
            
            # Step 5: Get final active/inactive counts
            final_counts = get_active_inactive_counts_web(conn)
            logger.info(f"Web final counts: {final_counts}")
            
            # Step 6: Calculate processing time
            processing_time = (datetime.now() - start_time).total_seconds()
            
            # Step 7: Insert comprehensive metadata
            etl_stats = {
                'records_inserted': upsert_results['inserted'],
                'records_updated': upsert_results['updated'],
                'records_skipped': skipped_count,
                'active_count': final_counts['active_count'],
                'inactive_count': final_counts['inactive_count'],
                'processing_time_seconds': round(processing_time, 2)
            }
            insert_api_metadata_web(conn, total, page, pull_date, etl_stats)
            
            # Commit transaction
            conn.commit()
            logger.info("Web transaction committed successfully with metadata")
            
            # Note: Change detection and notifications are handled by API refresh
            # to avoid sending duplicate notifications to users
            logger.info("Web data changes will be included in next API refresh notifications")
            
    except Exception as e:
        logger.error(f"Web: Database error during import: {str(e)}")
        raise Exception(f"Database error: {str(e)}")
    
    # Return enhanced summary
    return ImportSummary(
        status="success",
        total_records_in_file=len(items),
        records_inserted=upsert_results["inserted"],
        records_skipped=skipped_count,
        skipped_reasons=skipped_reasons,
        pull_date=str(pull_date),
        processing_time_seconds=round(processing_time, 2)
    )


def get_active_inactive_counts(conn: Connection) -> Dict[str, int]:
    """
    Get current counts of active and inactive records.
    Updated to use valid_to instead of just is_active for accuracy.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE valid_to IS NULL AND change_type != 'REMOVED') as active_count,
                COUNT(*) FILTER (WHERE valid_to IS NOT NULL OR change_type = 'REMOVED') as inactive_count,
                COUNT(DISTINCT uid) as unique_uids
            FROM tbl_bolo
        """)
        result = cur.fetchone()
        return {
            "active_count": result[0] or 0,
            "inactive_count": result[1] or 0,
            "unique_uids": result[2] or 0
        }


def get_active_inactive_counts_web(conn: Connection) -> Dict[str, int]:
    """
    Get current counts of active and inactive records in tbl_bolo_web.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                COUNT(*) FILTER (WHERE valid_to IS NULL AND change_type != 'REMOVED') as active_count,
                COUNT(*) FILTER (WHERE valid_to IS NOT NULL OR change_type = 'REMOVED') as inactive_count,
                COUNT(DISTINCT uid) as unique_uids
            FROM tbl_bolo_web
        """)
        result = cur.fetchone()
        return {
            "active_count": result[0] or 0,
            "inactive_count": result[1] or 0,
            "unique_uids": result[2] or 0
        }


async def fetch_page_with_retry(client: httpx.AsyncClient, url: str, params: dict, page: int, max_retries: int = 3) -> dict:
    """
    Fetch a single page from the FBI API with retry logic.
    Retries up to max_retries times on failure.
    """
    params_with_page = {**params, 'page': page}
    
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Fetching page {page} (attempt {attempt}/{max_retries})")
            response = await client.get(url, params=params_with_page)
            response.raise_for_status()
            logger.info(f"Successfully fetched page {page}")
            return response.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.warning(f"Error fetching page {page} on attempt {attempt}: {str(e)}")
            if attempt == max_retries:
                logger.error(f"Failed to fetch page {page} after {max_retries} attempts")
                raise HTTPException(
                    status_code=500, 
                    detail=f"Failed to fetch page {page} after {max_retries} attempts: {str(e)}"
                )
            # Wait before retrying (exponential backoff)
            await asyncio.sleep(2 ** attempt)

async def fetch_all_pages(client: httpx.AsyncClient, url: str, params: dict) -> dict:
    """
    Fetch all pages from the FBI Wanted API.
    Returns a combined response with all items.
    """
    logger.info("Starting to fetch all pages")
    
    # Fetch first page to determine total count
    logger.info("Fetching first page to determine total records")
    first_page = await fetch_page_with_retry(client, url, params, page=1)
    
    total = first_page.get('total', 0)
    logger.info(f"Total records: {total}")
    
    if total == 0:
        logger.info("No records found")
        return first_page
    
    # Calculate number of pages (20 items per page)
    items_per_page = 20
    total_pages = total // items_per_page
    if total % items_per_page > 0:
        total_pages += 1
    
    logger.info(f"Total pages to fetch: {total_pages}")
    
    # Start with items from first page
    all_items = first_page.get('items', [])
    
    # Fetch remaining pages
    for page_num in range(2, total_pages + 1):
        # Sleep between requests to avoid rate limiting
        logger.info(f"Sleeping 2 seconds before fetching page {page_num}")
        await asyncio.sleep(2)
        
        page_data = await fetch_page_with_retry(client, url, params, page=page_num)
        page_items = page_data.get('items', [])
        all_items.extend(page_items)
        logger.info(f"Accumulated {len(all_items)} items so far")
    
    logger.info(f"Finished fetching all pages. Total items: {len(all_items)}")
    
    # Return combined response
    return {
        'total': total,
        'items': all_items,
        'page': 1  # Represent as single combined page
    }

# FastAPI Router
router = APIRouter(prefix="/v1/etl", tags=["Data Import"], include_in_schema=True)

@router.get(
    "/load", 
    response_model=ImportSummary, 
    status_code=status.HTTP_200_OK,
    summary="Load FBI Wanted API data from File",
    description="Import FBI Wanted API data from JSON file on server."
    )
async def data_load(
    run_link_validation: bool = Query(
        default=True, 
        description="Run link validation after data load"
    ),
    generate_archive: bool = Query(
        default=True,
        description="Download files and generate ZIP archive after validation"
    ),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Import FBI Wanted API data from a JSON file on the server
    
    **Access:** ADMIN role only
    
    Parameters:
    - run_link_validation: If True, automatically validate all URLs after load
    - generate_archive: If True, download files and create ZIP archive (requires link validation)
    
    Returns a summary of the import operation including counts and any errors.
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"] 
    
    link_validation_results = None
    archive_results = None
    
    try:
        pull_date = date.today()
        file_path = "data/bolo-api-data.json"

        # Perform import
        summary = import_data_set(file_path, pull_date)
        
        # Run link validation if requested
        if run_link_validation:
            try:
                logger.info("Starting link validation after data load")
                link_validation_results = await validate_links_from_file(file_path)
                logger.info(f"Link validation complete: {link_validation_results.get('total_urls', 0)} URLs checked")
                
                # Generate archive if requested (only after successful validation)
                if generate_archive:
                    try:
                        logger.info("Starting file download and archive generation")
                        with get_db_connection() as conn:
                            download_results = await download_files_for_archive(conn)
                        logger.info(f"Download complete: {download_results.get('total_files', 0)} files")
                        
                        archive_results = create_documents_archive()
                        logger.info(f"Archive created: {archive_results.get('archive_path')}")
                    except Exception as e:
                        logger.error(f"Archive generation error (non-fatal): {str(e)}")
                        archive_results = {"error": str(e)}
                        
            except Exception as e:
                logger.error(f"Link validation error (non-fatal): {str(e)}")
                link_validation_results = {"error": str(e)}
        
        # Return summary (ImportSummary model - link validation and archive logged separately)
        return summary
        
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Import has failed: {str(e)}"
            )

@router.get(
    "/load_web", 
    response_model=ImportSummary, 
    status_code=status.HTTP_200_OK,
    summary="Load Web-Scraped FBI Wanted data from File",
    description="Import web-scraped FBI Wanted data from JSON file on server."
    )
async def data_load_web(
    run_link_validation: bool = Query(
        default=True, 
        description="Run link validation after data load"
    ),
    generate_archive: bool = Query(
        default=True,
        description="Download files and generate ZIP archive after validation"
    ),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Import web-scraped FBI Wanted data from a JSON file on the server.
    
    **Access:** ADMIN role only
    
    **File:** data/fbi-wanted-api-data-web.json
    
    **Note:** This endpoint does NOT process notifications.
    Notifications are handled by /full_refresh (API) which covers both sources.
    Run /full_refresh after this to notify users about changes.
    
    Parameters:
    - run_link_validation: If True, automatically validate all URLs after load
    - generate_archive: If True, download files and create ZIP archive (requires link validation)
    
    Returns a summary of the import operation including counts and any errors.
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"] 
    
    link_validation_results = None
    archive_results = None
    
    try:
        pull_date = date.today()
        file_path = "data/fbi-wanted-api-data-web.json"

        # Perform import to tbl_bolo_web
        summary = import_data_set_web(file_path, pull_date)
        
        # Run link validation if requested (uses separate table)
        if run_link_validation:
            try:
                logger.info("Starting web link validation after data load")
                link_validation_results = await validate_links_from_file_web(file_path)
                logger.info(f"Web link validation complete: {link_validation_results.get('total_urls_extracted', 0)} URLs checked")
                
                # Generate archive if requested (only after successful validation)
                if generate_archive:
                    try:
                        logger.info("Starting file download and archive generation for web data")
                        with get_db_connection() as conn:
                            download_results = await download_files_for_archive(conn)
                        logger.info(f"Download complete: {download_results.get('total_files', 0)} files")
                        
                        archive_results = create_documents_archive()
                        logger.info(f"Archive created: {archive_results.get('archive_path')}")
                    except Exception as e:
                        logger.error(f"Web archive generation error (non-fatal): {str(e)}")
                        archive_results = {"error": str(e)}
                        
            except Exception as e:
                logger.error(f"Web link validation error (non-fatal): {str(e)}")
                link_validation_results = {"error": str(e)}
        
        # Return summary
        return summary
        
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
            )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Web import has failed: {str(e)}"
            )

@router.get(
    "/extract",
    summary="Extract FBI Wanted API data from API",
    description="Extract FBI Wanted API data and save to file in JSON or CSV format."
    )
async def get_wanted(
    request: Request,
    format: Literal["json", "csv"] = Query(default="json", description="Output format"),
    size: Literal["default", "all"] = Query(default="default", description="Data size - 'default' for single page, 'all' for all records"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Extract FBI Wanted API data and save to file in JSON or CSV format.
    
    **Access:** ADMIN role only
    
    Parameters:
    - format: Output format - 'json' (default) or 'csv'
    - size: Data size - 'default' (single page) or 'all' (all records across all pages)
    - All other query parameters are passed through to the FBI API
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"]
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Filter out our custom parameters before passing to FBI API
            fbi_params = {
                k: v for k, v in request.query_params.items()
                if k not in ['format', 'size', 'page']
            }
            
            # Fetch data based on size parameter
            if size == "all":
                data = await fetch_all_pages(client, FBI_API_URL, fbi_params)
            else:
                # Default: fetch single page
                response = await client.get(FBI_API_URL, params=fbi_params)
                response.raise_for_status()
                data = response.json()
        
        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Request error: {str(e)}")
        except httpx.HTTPStatusError as e:
            logger.error(f"FBI API error: {str(e)}")
            raise HTTPException(status_code=e.response.status_code, detail=f"FBI API error: {str(e)}")
        
        # Save as JSON file
        if format == "json":
            filename = "data/bolo-api-data.json"
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                logger.info(f"Saved JSON file with {len(data.get('items', []))} items")
                return {"message": f"Extracted data to {filename}"}
            except Exception as e:
                logger.error(f"Error saving JSON file: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Error saving JSON file: {str(e)}")
        
        # Save as CSV file
        if format == "csv":
            filename = "data/bolo-api-data.csv"
            try:
                logger.info("Converting to CSV format")
                # Load the schema and extract simple fields
                schema_path = "data/fbi-wanted-api-schema.json"
                simple_fields = load_simple_fields_from_schema(schema_path)
                
                # Convert to CSV
                csv_content = convert_to_csv(data, simple_fields)
                
                # Save to file
                with open(filename, 'w', encoding='utf-8', newline='') as f:
                    f.write(csv_content)
                
                logger.info(f"Saved CSV file with {len(data.get('items', []))} items")
                return {"message": f"Extracted data to {filename}"}
            except Exception as e:
                logger.error(f"CSV conversion error: {str(e)}")
                raise HTTPException(status_code=500, detail=f"CSV conversion error: {str(e)}")

@router.get(
    "/full_refresh",
    summary="Full Data Refresh",
    description="Perform a full refresh: extract all FBI Wanted API data to JSON file, then load it."
    )
async def full_refresh(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Perform a full refresh: extract all FBI Wanted API data to JSON file, then load it.
    
    This endpoint calls:
    1. /extract with format=json and size=all
    2. /load to process the extracted data
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"] 
    try:
        logger.info("Starting full refresh process")
        
        # Step 1: Call extract endpoint with format=json and size=all
        logger.info("Step 1: Extracting all data to JSON file")
        extract_response = await get_wanted(
            request=request,
            format="json",
            size="all",
            current_user=current_user
            )
        logger.info(f"Extract completed: {extract_response}")
        
        # Step 2: Call load endpoint
        logger.info("Step 2: Loading extracted data")
        load_response = await data_load(current_user=current_user)
        logger.info(f"Load completed: {load_response}")
        logger.info("Step 3: Processing notifications")

        try:
            notification_results = process_pending_notifications()
            logger.info(f"Notification processing complete: {notification_results}")
        except Exception as e:
            logger.error(f"Notification processing error (non-fatal): {str(e)}")
            notification_results = {"error": str(e)}
        
        logger.info("Full refresh process completed successfully")
        return {
            "message": "Full refresh completed successfully",
            "extract": extract_response,
            "load": load_response,
            "notifications": notification_results  # ADD THIS
            }
        
    except HTTPException as e:
        logger.error(f"Full refresh failed with HTTP error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Full refresh failed with unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Full refresh error: {str(e)}")

@router.post(
    "/full_refresh_web",
    summary="Full Web Data Refresh",
    description="Perform a full refresh of web-scraped FBI Wanted data (no notifications)."
    )
async def full_refresh_web(
    request: Request,
    run_link_validation: bool = Query(
        default=True, 
        description="Run link validation after data load"
    ),
    generate_archive: bool = Query(
        default=False,
        description="Download files and generate ZIP archive after validation"
    ),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Perform a full refresh of web-scraped FBI Wanted data.
    
    **Access:** ADMIN role only
    
    **Note:** This endpoint does NOT process notifications.
    Notifications are handled by /full_refresh (API) which covers both sources.
    
    This endpoint:
    1. Loads web data from data/fbi-wanted-api-data-web.json
    2. Validates links (optional)
    3. Generates archive (optional)
    
    To send notifications after web refresh, run /full_refresh afterward.
    
    Parameters:
    - run_link_validation: Validate all URLs after load (default: True)
    - generate_archive: Create ZIP archive of documents (default: False)
    
    Returns results from load operation.
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"]
    
    try:
        logger.info("Starting web data refresh (no notifications)")
        
        # Load web data (no notification processing)
        logger.info("Loading web-scraped data")
        load_response = await data_load_web(
            run_link_validation=run_link_validation,
            generate_archive=generate_archive,
            current_user=current_user
        )
        logger.info(f"Web load completed: {load_response}")
        
        logger.info("Web refresh completed (notifications will be handled by API refresh)")
        return {
            "message": "Web data refresh completed successfully",
            "load": load_response,
            "note": "Notifications not processed. Run /full_refresh to notify users about all changes."
        }
        
    except HTTPException as e:
        logger.error(f"Full web refresh failed with HTTP error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Full web refresh failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Full web refresh error: {str(e)}"
        )

@router.post(
    "/full_refresh_all",
    summary="Full Refresh (API + Web)",
    description="Perform a full refresh of both API and web-scraped FBI Wanted data with unified notifications."
    )
async def full_refresh_all(
    request: Request,
    run_link_validation: bool = Query(
        default=True, 
        description="Run link validation for both API and web data"
    ),
    generate_archive: bool = Query(
        default=False,
        description="Generate archives for both API and web data"
    ),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Perform a full refresh of both FBI API data and web-scraped data.
    
    **Access:** ADMIN role only
    
    **Notification Strategy:**
    - Web data is loaded first (no notifications)
    - API data is loaded second (notifications cover BOTH sources)
    - Users receive ONE consolidated notification covering all changes
    
    This endpoint runs the complete refresh workflow:
    1. Load web data into tbl_bolo_web (if file exists)
    2. Extract all FBI API data to JSON file
    3. Load API data into tbl_bolo
    4. Process notifications for ALL changes (both sources)
    
    This is equivalent to running:
    - /v1/etl/full_refresh_web (no notifications)
    - /v1/etl/full_refresh (with notifications)
    
    Parameters:
    - run_link_validation: Validate URLs for both sources (default: True)
    - generate_archive: Create ZIP archives for both sources (default: False)
    
    Returns combined results from both refresh operations.
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"]
    
    results = {
        "web_refresh": None,
        "api_refresh": None
    }
    
    try:
        logger.info("Starting full refresh for both API and web data")
        
        # Step 1: Refresh web data FIRST (no notifications)
        logger.info("=== Phase 1: Web Data Refresh (no notifications) ===")
        try:
            # Check if web data file exists before attempting
            web_file_path = Path("data/fbi-wanted-api-data-web.json")
            if web_file_path.exists():
                web_result = await full_refresh_web(
                    request=request,
                    run_link_validation=run_link_validation,
                    generate_archive=generate_archive,
                    current_user=current_user
                )
                results["web_refresh"] = web_result
                logger.info("Web refresh completed successfully")
            else:
                logger.warning("Web data file not found, skipping web refresh")
                results["web_refresh"] = {
                    "skipped": True,
                    "reason": "Web data file not found: data/fbi-wanted-api-data-web.json"
                }
        except Exception as e:
            logger.error(f"Web refresh failed: {str(e)}")
            results["web_refresh"] = {"error": str(e)}
            # Continue with API refresh even if web fails
        
        # Step 2: Refresh API data SECOND (with notifications covering BOTH sources)
        logger.info("=== Phase 2: API Data Refresh (notifications for all changes) ===")
        try:
            api_result = await full_refresh(request=request, current_user=current_user)
            results["api_refresh"] = api_result
            logger.info("API refresh completed successfully with unified notifications")
        except Exception as e:
            logger.error(f"API refresh failed: {str(e)}")
            results["api_refresh"] = {"error": str(e)}
        
        logger.info("Full refresh (all sources) completed")
        return {
            "message": "Full refresh completed for all data sources",
            "notification_strategy": "Unified notifications sent covering both API and web changes",
            "results": results
        }
        
    except HTTPException as e:
        logger.error(f"Full refresh all failed with HTTP error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Full refresh all failed with unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Full refresh all error: {str(e)}"
        )
    
@router.get(
    "/metadata",
    summary="ETL Metadata History",
    description="View ETL run statistics and performance metrics."
    )
async def get_etl_metadata(
    limit: int = Query(default=30, ge=1, le=365, description="Number of recent pulls to return"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get ETL metadata showing statistics from recent data pulls.
    
    **Access:** ADMIN role only
    
    Returns detailed statistics including:
    - Records inserted, updated, skipped
    - Active/inactive counts
    - Processing time
    - FBI API totals
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        pull_date,
                        total_records as fbi_reported_total,
                        page,
                        pull_timestamp,
                        records_inserted,
                        records_updated,
                        records_skipped,
                        active_count,
                        inactive_count,
                        processing_time_seconds,
                        ROUND(processing_time_seconds / 60.0, 2) as processing_time_minutes
                    FROM tbl_bolo_control
                    ORDER BY pull_date DESC
                    LIMIT %s
                """, (limit,))
                
                results = cur.fetchall()
                
                # Calculate some summary stats
                if results:
                    total_inserts = sum(r['records_inserted'] or 0 for r in results)
                    total_updates = sum(r['records_updated'] or 0 for r in results)
                    avg_processing = sum(r['processing_time_seconds'] or 0 for r in results) / len(results)
                    
                    summary = {
                        "total_pulls": len(results),
                        "date_range": {
                            "earliest": str(results[-1]['pull_date']) if results else None,
                            "latest": str(results[0]['pull_date']) if results else None
                        },
                        "totals": {
                            "records_inserted": total_inserts,
                            "records_updated": total_updates,
                            "avg_processing_time_seconds": round(avg_processing, 2)
                        },
                        "current_state": {
                            "active_count": results[0]['active_count'],
                            "inactive_count": results[0]['inactive_count'],
                            "total_records": results[0]['active_count'] + results[0]['inactive_count']
                        }
                    }
                else:
                    summary = {"message": "No metadata available"}
                
                return {
                    "summary": summary,
                    "pulls": [dict(r) for r in results]
                }
                
    except Exception as e:
        logger.error(f"Error retrieving ETL metadata: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve metadata: {str(e)}"
        )

@router.get(
    "/metadata_web",
    summary="Web Data ETL Metadata History",
    description="View ETL run statistics and performance metrics for web-scraped data."
    )
async def get_etl_metadata_web(
    limit: int = Query(default=30, ge=1, le=365, description="Number of recent pulls to return"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get ETL metadata showing statistics from recent web data pulls.
    
    **Access:** ADMIN role only
    
    Returns detailed statistics including:
    - Records inserted, updated, skipped
    - Active/inactive counts
    - Processing time
    - Web scrape totals
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        pull_date,
                        total_records as web_scrape_total,
                        page,
                        pull_timestamp,
                        records_inserted,
                        records_updated,
                        records_skipped,
                        active_count,
                        inactive_count,
                        processing_time_seconds,
                        ROUND(processing_time_seconds / 60.0, 2) as processing_time_minutes
                    FROM tbl_bolo_control_web
                    ORDER BY pull_date DESC
                    LIMIT %s
                """, (limit,))
                
                results = cur.fetchall()
                
                # Calculate some summary stats
                if results:
                    total_inserts = sum(r['records_inserted'] or 0 for r in results)
                    total_updates = sum(r['records_updated'] or 0 for r in results)
                    avg_processing = sum(r['processing_time_seconds'] or 0 for r in results) / len(results)
                    
                    summary = {
                        "total_pulls": len(results),
                        "date_range": {
                            "earliest": str(results[-1]['pull_date']) if results else None,
                            "latest": str(results[0]['pull_date']) if results else None
                        },
                        "totals": {
                            "records_inserted": total_inserts,
                            "records_updated": total_updates,
                            "avg_processing_time_seconds": round(avg_processing, 2)
                        },
                        "current_state": {
                            "active_count": results[0]['active_count'],
                            "inactive_count": results[0]['inactive_count'],
                            "total_records": results[0]['active_count'] + results[0]['inactive_count']
                        }
                    }
                else:
                    summary = {"message": "No web metadata available"}
                
                return {
                    "summary": summary,
                    "pulls": [dict(r) for r in results]
                }
                
    except Exception as e:
        logger.error(f"Error retrieving web ETL metadata: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve web metadata: {str(e)}"
        )

@router.get(
    "/metadata_all",
    summary="Combined ETL Metadata (API + Web)",
    description="View combined ETL statistics from both API and web-scraped data sources."
    )
async def get_etl_metadata_all(
    limit: int = Query(default=30, ge=1, le=365, description="Number of recent pulls to return per source"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get combined ETL metadata from both API and web data sources.
    
    **Access:** ADMIN role only
    
    Returns side-by-side statistics for:
    - API data pulls (tbl_bolo_control)
    - Web data pulls (tbl_bolo_control_web)
    - Combined current state
    """
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get API metadata
                cur.execute("""
                    SELECT 
                        'api' as source,
                        pull_date,
                        total_records,
                        pull_timestamp,
                        records_inserted,
                        records_updated,
                        records_skipped,
                        active_count,
                        inactive_count,
                        processing_time_seconds
                    FROM tbl_bolo_control
                    ORDER BY pull_date DESC
                    LIMIT %s
                """, (limit,))
                api_results = cur.fetchall()
                
                # Get Web metadata
                cur.execute("""
                    SELECT 
                        'web' as source,
                        pull_date,
                        total_records,
                        pull_timestamp,
                        records_inserted,
                        records_updated,
                        records_skipped,
                        active_count,
                        inactive_count,
                        processing_time_seconds
                    FROM tbl_bolo_control_web
                    ORDER BY pull_date DESC
                    LIMIT %s
                """, (limit,))
                web_results = cur.fetchall()
                
                # Calculate combined current state
                api_current = api_results[0] if api_results else None
                web_current = web_results[0] if web_results else None
                
                combined_state = {
                    "api": {
                        "active_count": api_current['active_count'] if api_current else 0,
                        "inactive_count": api_current['inactive_count'] if api_current else 0,
                        "total_records": (api_current['active_count'] + api_current['inactive_count']) if api_current else 0,
                        "last_pull": str(api_current['pull_date']) if api_current else None
                    },
                    "web": {
                        "active_count": web_current['active_count'] if web_current else 0,
                        "inactive_count": web_current['inactive_count'] if web_current else 0,
                        "total_records": (web_current['active_count'] + web_current['inactive_count']) if web_current else 0,
                        "last_pull": str(web_current['pull_date']) if web_current else None
                    },
                    "combined": {
                        "total_active": (api_current['active_count'] if api_current else 0) + 
                                      (web_current['active_count'] if web_current else 0),
                        "total_inactive": (api_current['inactive_count'] if api_current else 0) + 
                                        (web_current['inactive_count'] if web_current else 0),
                        "total_records": ((api_current['active_count'] + api_current['inactive_count']) if api_current else 0) +
                                       ((web_current['active_count'] + web_current['inactive_count']) if web_current else 0)
                    }
                }
                
                return {
                    "current_state": combined_state,
                    "api_pulls": [dict(r) for r in api_results],
                    "web_pulls": [dict(r) for r in web_results]
                }
                
    except Exception as e:
        logger.error(f"Error retrieving combined ETL metadata: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve combined metadata: {str(e)}"
        )
      
@router.get(
    "/process_notifications",
    summary="Process Pending Notifications",
    description="Process and send pending BoloDoc notifications to opted-in premium users."
    )
async def process_notifications_endpoint(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Process and send any pending notifications without running a full refresh.
    
    **Access:** ADMIN role only
    
    This is useful for:
    - Retrying failed notifications
    - Testing the notification system
    - Manually triggering notifications after a refresh
    """
    try:
        logger.info("Processing notifications (manual trigger)")
        
        notification_results = process_pending_notifications()
        
        return {
            "message": "Notification processing complete",
            "results": notification_results
        }
        
    except Exception as e:
        logger.error(f"Notification processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Notification processing error: {str(e)}")
    
# =============================================================================
# LINK VALIDATION ENDPOINTS
# =============================================================================

@router.get(
    "/validate_links",
    summary="Validate All URLs in BoloDoc aata",
    description="Extract and validate all URLs from the FBI Wanted API data file."
    )
async def validate_links_endpoint(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Extract all URLs from FBI BoloDoc data and validate their accessibility.
    
    **Access:** ADMIN role only
    
    This endpoint:
    1. Reads the current FBI Wanted API data file
    2. Extracts all URLs (pathId, url, files, images)
    3. Validates each URL using HEAD requests
    4. Stores results in tbl_bolo_link_check
    
    URLs are validated asynchronously with rate limiting to avoid
    overwhelming FBI servers.
    
    Returns summary statistics including success/failure/timeout counts.
    """
    try:
        file_path = "data/bolo-api-data.json"
        
        logger.info("Starting link validation process")
        summary = await validate_links_from_file(file_path)
        
        return summary
        
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="FBI Wanted API data file not found. Run /extract first."
            )
    except Exception as e:
        logger.error(f"Link validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Link validation failed: {str(e)}"
            )


@router.get(
    "/link_status",
    summary="Link Validation Status Summary",
    description="View summary statistics from link validation results."
    )
async def get_link_status(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get summary statistics from the link validation table.
    
    **Access:** ADMIN role only
    
    Returns:
    - Total links checked
    - Counts by result (success, failure, timeout)
    - Counts by HTTP response code
    - Counts by field type (url, pathId, images, files)
    - Last update timestamp
    """
    try:
        with get_db_connection() as conn:
            summary = get_link_check_summary(conn)
            return summary
            
    except Exception as e:
        logger.error(f"Error getting link status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get link status: {str(e)}"
            )


@router.get(
    "/link_failures",
    summary="List Failed Links",
    description="View list of URLs that failed validation."
    )
async def get_link_failures(
    limit: int = Query(default=100, ge=1, le=1000, description="Maximum results to return"),
    include_timeouts: bool = Query(default=True, description="Include timeout results"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get list of URLs that failed validation or timed out.
    
    **Access:** ADMIN role only
    
    Useful for identifying:
    - Broken links in FBI Wanted API data
    - URLs that may have moved or been removed
    - Network connectivity issues
    
    Parameters:
    - limit: Maximum number of results (1-1000)
    - include_timeouts: Whether to include timeout results
    """
    try:
        with get_db_connection() as conn:
            failures = get_failed_links(conn, limit, include_timeouts)
            return {
                "count": len(failures),
                "include_timeouts": include_timeouts,
                "failures": failures
            }
            
    except Exception as e:
        logger.error(f"Error getting link failures: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get link failures: {str(e)}"
            )
    
# =============================================================================
# CACHE MANAGEMENT ENDPOINTS
# =============================================================================

@router.get(
    "/cache_stats",
    summary="View Cache Statistics",
    description="View file cache statistics including file count and total size."
    )
async def get_cache_statistics(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get statistics about the download cache directory.
    
    **Access:** ADMIN role only
    
    Returns:
    - File count in cache
    - Total size (bytes and MB)
    - Files by extension
    """
    try:
        stats = get_cache_stats()
        return stats
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get cache stats: {str(e)}"
            )


@router.delete(
    "/cache",
    summary="Clear Download Cache",
    description="Delete all cached files to force re-download."
    )
async def clear_download_cache(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Delete all cached download files.
    
    **Access:** ADMIN role only
    
    Use this to force re-download of all files on next archive generation.
    
    Returns count of deleted files and bytes freed.
    """
    try:
        result = clear_cache()
        return {
            "status": "success",
            "message": f"Cleared {result['files_deleted']} cached files",
            **result
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(e)}"
            )


# =============================================================================
# ARCHIVE MANAGEMENT ENDPOINTS
# =============================================================================

@router.post(
    "/download_files",
    summary="Download Files to Cache",
    description="Download all validated files to cache directory."
    )
async def download_files_endpoint(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Download all files from validated URLs to local cache.
    
    **Access:** ADMIN role only
    
    This step must complete before archive generation.
    Uses existing cached files when available.
    
    Returns statistics on files downloaded vs cached.
    """
    try:
        with get_db_connection() as conn:
            result = await download_files_for_archive(conn)
        
        return result
        
    except Exception as e:
        logger.error(f"Error downloading files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"File download failed: {str(e)}"
            )


@router.post(
    "/create_archive",
    summary="Create Documents Archive",
    description="Generate ZIP archive from cached files."
    )
async def create_archive_endpoint(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Create the BOLO documents ZIP archive.
    
    **Access:** ADMIN role only
    
    Prerequisites:
    - Link validation must have been run
    - Files must have been downloaded to cache
    
    Creates bolodoc_files.zip with:
    - Per-person folders (LASTNAME_FIRSTNAME_uid/)
    - info.txt summary per person
    - All downloaded documents and images
    - Root manifest.txt with statistics
    
    Returns archive creation statistics.
    """
    try:
        result = create_documents_archive()
        
        if result['status'] != 'success':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get('message', 'Archive creation failed')
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating archive: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Archive creation failed: {str(e)}"
            )


@router.get(
    "/archive_status",
    summary="Archive Status",
    description="Get information about the current archive file."
    )
async def get_archive_status(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Get status and information about the current archive file.
    
    **Access:** ADMIN role only
    
    Returns:
    - Archive file path
    - File size
    - Creation/modification timestamps
    - Whether archive exists
    """
    try:
        info = get_archive_info()
        
        if not info:
            return {
                "exists": False,
                "message": "No archive file exists. Run create_archive first."
            }
        
        return info
        
    except Exception as e:
        logger.error(f"Error getting archive status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get archive status: {str(e)}"
            )


@router.post(
    "/generate_full_archive",
    summary="Full Archive Generation",
    description="Run complete archive generation process: validate links, download files, create archive."
    )
async def generate_full_archive(
    skip_validation: bool = Query(
        default=False,
        description="Skip link validation (use existing validation data)"
    ),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Run complete archive generation pipeline.
    
    **Access:** ADMIN role only
    
    Steps:
    1. Validate all URLs (unless skip_validation=True)
    2. Download all validated files to cache
    3. Create ZIP archive
    
    This is equivalent to running:
    - /validate_links
    - /download_files
    - /create_archive
    
    Returns combined results from all steps.
    """
    results = {
        "validation": None,
        "download": None,
        "archive": None
    }
    
    try:
        # Step 1: Validate links (unless skipped)
        if not skip_validation:
            logger.info("Step 1/3: Validating links")
            file_path = "data/bolo-api-data.json"
            results["validation"] = await validate_links_from_file(file_path)
        else:
            results["validation"] = {"skipped": True, "message": "Using existing validation data"}
        
        # Step 2: Download files
        logger.info("Step 2/3: Downloading files")
        with get_db_connection() as conn:
            results["download"] = await download_files_for_archive(conn)
        
        # Step 3: Create archive
        logger.info("Step 3/3: Creating archive")
        results["archive"] = create_documents_archive()
        
        return {
            "status": "success",
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Full archive generation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Archive generation failed: {str(e)}"
            )

# =============================================================================
# UTILITY FUNCTIONS FOR HISTORY QUERIES
# =============================================================================

def get_person_version_history(conn: Connection, uid: str, table: str = 'tbl_bolo') -> List[Dict]:
    """
    Get complete version history for a specific person.
    
    Args:
        conn: Database connection
        uid: Person's unique identifier
        table: Which table to query ('tbl_bolo' or 'tbl_bolo_web')
        
    Returns:
        List of version records ordered by version_number descending
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"""
            SELECT 
                version_number,
                change_type,
                valid_from,
                valid_to,
                status,
                reward_max,
                poster_classification,
                title,
                modified as fbi_modified,
                first_seen_date,
                last_seen_date,
                content_hash
            FROM {table}
            WHERE uid = %s
            ORDER BY version_number DESC
        """, (uid,))
        return [dict(row) for row in cur.fetchall()]


def get_changes_by_date(conn: Connection, change_date: date, table: str = 'tbl_bolo') -> Dict[str, List[str]]:
    """
    Get all changes that occurred on a specific date, grouped by change type.
    
    Args:
        conn: Database connection
        change_date: Date to query
        table: Which table to query
        
    Returns:
        Dict mapping change_type to list of UIDs
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"""
            SELECT change_type, uid, title
            FROM {table}
            WHERE valid_from = %s
            ORDER BY change_type, title
        """, (change_date,))
        
        results = {'NEW': [], 'MODIFIED': [], 'REMOVED': [], 'RETURNED': []}
        for row in cur.fetchall():
            change_type = row['change_type']
            if change_type in results:
                results[change_type].append({'uid': row['uid'], 'title': row['title']})
        
        return results


def get_daily_change_summary(conn: Connection, days: int = 30, table: str = 'tbl_bolo') -> List[Dict]:
    """
    Get daily summary of changes for the last N days.
    
    Args:
        conn: Database connection
        days: Number of days to look back
        table: Which table to query
        
    Returns:
        List of daily summaries with counts by change type
    """
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(f"""
            SELECT 
                valid_from as change_date,
                COUNT(*) FILTER (WHERE change_type = 'NEW') as new_count,
                COUNT(*) FILTER (WHERE change_type = 'MODIFIED') as modified_count,
                COUNT(*) FILTER (WHERE change_type = 'REMOVED') as removed_count,
                COUNT(*) FILTER (WHERE change_type = 'RETURNED') as returned_count,
                COUNT(*) as total_changes
            FROM {table}
            WHERE valid_from >= CURRENT_DATE - INTERVAL '%s days'
            GROUP BY valid_from
            ORDER BY valid_from DESC
        """, (days,))
        return [dict(row) for row in cur.fetchall()]