import httpx
import json
import logging
import csv
import asyncio
import os
import re

from config import DB_CONFIG
from typing import Literal
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any
from io import StringIO
from contextlib import contextmanager 

import psycopg2
from psycopg2.extras import execute_values
from psycopg2.extensions import connection as Connection
from fastapi import APIRouter, HTTPException, status, Response, Request, Query, Depends
from pydantic import BaseModel, Field
from fastapi import APIRouter

# Import auth utilities
from auth import UserRole
from jwt_auth import require_jwt_role

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

FBI_API_URL = "https://api.fbi.gov/wanted/v1/list"

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        logger.info(f"Sleeping 3 seconds before fetching page {page_num}")
        await asyncio.sleep(3)
        
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


def extract_array_field(data: Dict, field: str) -> Optional[List[str]]:
    """Extract array field, converting None to empty list for PostgreSQL"""
    value = data.get(field)
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return None


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
    html_tags = re.compile(r'</?(?:p|br|b|i|u|strong|em|span|div)(?:\s[^>]*)?>|Â', re.IGNORECASE)
    
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
    Process a single wanted person record into database-ready format
    Returns None if the record should be skipped
    """
    
    uid = item.get('uid')
    if not uid:
        return None

    # Create cleaned version of full_data
    full_data_clean = clean_json_recursive(item)

    # print(full_data_clean)

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
        'data_pull_date': pull_date,
        'first_seen_date': pull_date,
        'last_seen_date': pull_date,
        'is_active': True
    }


def insert_api_metadata(conn: Connection, total: int, page: int, pull_date: date):
    """Insert API pull metadata"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO api_pull_metadata (pull_date, total_records, page, pull_timestamp)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (pull_date) 
            DO UPDATE SET 
                total_records = EXCLUDED.total_records,
                page = EXCLUDED.page,
                pull_timestamp = NOW()
        """, (pull_date, total, page))


def bolo_insert(conn: Connection, records: List[Dict[str, Any]]) -> int:
    """
    Batch upsert wanted persons records using MERGE logic
    Returns number of records inserted or updated
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
    
    # Non-key columns for UPDATE clause
    non_key_columns = [col for col in columns if col not in ['uid', 'data_pull_date']]

    # Prepare values for batch insert
    values = []
    for record in records:
        row = tuple(record.get(col) for col in columns)
        values.append(row)
    
    with conn.cursor() as cur:
        # UPSERT with ON CONFLICT DO UPDATE
        upsert_query = f"""
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
            ON CONFLICT (uid, data_pull_date) 
            DO UPDATE SET
                age_max = EXCLUDED.age_max,
                age_min = EXCLUDED.age_min,
                aliases = EXCLUDED.aliases,
                build = EXCLUDED.build,
                caution = EXCLUDED.caution,
                complexion = EXCLUDED.complexion,
                coordinates = EXCLUDED.coordinates,
                dates_of_birth_used = EXCLUDED.dates_of_birth_used,
                description = EXCLUDED.description,
                details = EXCLUDED.details,
                eyes = EXCLUDED.eyes,
                eyes_raw = EXCLUDED.eyes_raw,
                field_offices = EXCLUDED.field_offices,
                first_seen_date = EXCLUDED.first_seen_date,
                full_data = EXCLUDED.full_data,
                full_data_clean = EXCLUDED.full_data_clean,
                hair = EXCLUDED.hair,
                hair_raw = EXCLUDED.hair_raw,
                height_max = EXCLUDED.height_max,
                height_min = EXCLUDED.height_min,
                is_active = EXCLUDED.is_active,
                languages = EXCLUDED.languages,
                last_seen_date = EXCLUDED.last_seen_date,
                legat_names = EXCLUDED.legat_names,
                locations = EXCLUDED.locations,
                modified = EXCLUDED.modified,
                nationality = EXCLUDED.nationality,
                ncic = EXCLUDED.ncic,
                occupations = EXCLUDED.occupations,
                path = EXCLUDED.path,
                pathid = EXCLUDED.pathid,
                person_classification = EXCLUDED.person_classification,
                place_of_birth = EXCLUDED.place_of_birth,
                possible_countries = EXCLUDED.possible_countries,
                possible_states = EXCLUDED.possible_states,
                poster_url = EXCLUDED.poster_url,
                poster_classification = EXCLUDED.poster_classification,
                publication = EXCLUDED.publication,
                race = EXCLUDED.race,
                race_raw = EXCLUDED.race_raw,
                remarks = EXCLUDED.remarks,
                reward_max = EXCLUDED.reward_max,
                reward_min = EXCLUDED.reward_min,
                reward_text = EXCLUDED.reward_text,
                scars_and_marks = EXCLUDED.scars_and_marks,
                sex = EXCLUDED.sex,
                status = EXCLUDED.status,
                subjects = EXCLUDED.subjects,
                suspects = EXCLUDED.suspects,
                title = EXCLUDED.title,
                url = EXCLUDED.url,
                warning_message = EXCLUDED.warning_message,
                weight = EXCLUDED.weight,
                weight_max = EXCLUDED.weight_max,
                weight_min = EXCLUDED.weight_min,
                updated_at = NOW()
        """
        execute_values(cur, upsert_query, values, page_size=100)
        return cur.rowcount


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
        cur.execute("CALL prc_clean_text()")
        cur.execute("CALL prc_clean_array()")
        cur.execute("CALL prc_clean_jsonb()")
        cur.execute("CALL prc_prune()")

def import_data_set(file_path: str, pull_date: date) -> ImportSummary:
    """
    Main import function - reads JSON file and imports to database
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
        return ImportSummary(
            status="success",
            total_records_in_file=0,
            records_inserted=0,
            records_skipped=0,
            pull_date=str(pull_date),
            processing_time_seconds=(datetime.now() - start_time).total_seconds()
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
            # Insert metadata
            insert_api_metadata(conn, total, page, pull_date)
            
            # Insert wanted persons
            inserted_count = bolo_insert(conn, processed_records)
            
            # Update inactive records
            current_uids = [r['uid'] for r in processed_records]
            update_record_status(conn, current_uids, pull_date)
            
            # Commit transaction
            conn.commit()
            
    except Exception as e:
        raise Exception(f"Database error: {str(e)}")
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    return ImportSummary(
        status="success",
        total_records_in_file=len(items),
        records_inserted=inserted_count,
        records_skipped=skipped_count,
        skipped_reasons=skipped_reasons,
        pull_date=str(pull_date),
        processing_time_seconds=round(processing_time, 2)
    )

# FastAPI Router
router = APIRouter(prefix="/api/etl", tags=["Data Import"], include_in_schema=True)

@router.get(
    "/load", 
    response_model=ImportSummary, 
    status_code=status.HTTP_200_OK,
    summary="Load FBI Data from File",
    description="Import FBI wanted data from JSON file on server. **ADMIN ONLY**"
    )
async def data_load(
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Import FBI wanted data from a JSON file on the server
    
    **Access:** ADMIN role only
    
    Returns a summary of the import operation including counts and any errors.
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"] 
    try:
        pull_date = date.today()
        file_path = "data/fbi-wanted-api-data.json"

        # Perform import
        summary = import_data_set(file_path, pull_date)
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
    "/extract",
    summary="Extract FBI Data from API",
    description="Extract FBI wanted data and save to file in JSON or CSV format. **ADMIN ONLY**"
    )
async def get_wanted(
    request: Request,
    format: Literal["json", "csv"] = Query(default="json", description="Output format"),
    size: Literal["default", "all"] = Query(default="default", description="Data size - 'default' for single page, 'all' for all records"),
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Extract FBI wanted data and save to file in JSON or CSV format.
    
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
            filename = "data/fbi-wanted-api-data.json"
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
            filename = "data/fbi-wanted-api-data.csv"
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
    description="Perform a full refresh: extract all FBI wanted data to JSON file, then load it. **ADMIN ONLY**"
    )
async def full_refresh(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))
    ):
    """
    Perform a full refresh: extract all FBI wanted data to JSON file, then load it.
    
    **Access:** ADMIN role only
    
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
        
        logger.info("Full refresh process completed successfully")
        return {
            "message": "Full refresh completed successfully",
            "extract": extract_response,
            "load": load_response
        }
        
    except HTTPException as e:
        logger.error(f"Full refresh failed with HTTP error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Full refresh failed with unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Full refresh error: {str(e)}")