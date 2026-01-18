"""
Response Format Utilities for BoloDoc API

Provides conversion functions to transform JSON search results into
CSV, TXT, XML, and Parquet formats with appropriate MIME types.
"""

import csv
import io
import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from fastapi import Response, HTTPException, status


class ResponseFormat(str, Enum):
    """Supported response formats for search endpoints"""
    JSON = "json"
    CSV = "csv"
    TXT = "txt"
    XML = "xml"
    PARQUET = "parquet"


def validate_format_access(user_role: str, requested_format: ResponseFormat) -> None:
    """
    Validate that the user's role allows access to the requested format.
    
    Format access rules:
    - BASIC: JSON only
    - PREMIUM: JSON, CSV, TXT, XML, Parquet
    - ADMIN: JSON, CSV, TXT, XML, Parquet
    
    Args:
        user_role: The user's role (basic, premium, admin)
        requested_format: The requested response format
        
    Raises:
        HTTPException: 403 if user doesn't have access to the requested format
    """
    # Convert role to lowercase for comparison
    role_lower = user_role.lower() if isinstance(user_role, str) else user_role.value.lower()
    
    # BASIC users can only use JSON format
    if role_lower == "basic":
        if requested_format != ResponseFormat.JSON:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Format '{requested_format.value}' is only available to PREMIUM and ADMIN subscribers. "
                       f"BASIC users can only use JSON format. Upgrade to PREMIUM for CSV, TXT, XML, and Parquet formats."
            )
    
    # PREMIUM and ADMIN can use all formats (no restrictions)
    # No validation needed for premium/admin users


# Field office code to readable name mapping
FIELD_OFFICES = {
    "albany": "Albany",
    "albuquerque": "Albuquerque",
    "anchorage": "Anchorage",
    "atlanta": "Atlanta",
    "baltimore": "Baltimore",
    "birmingham": "Birmingham",
    "boston": "Boston",
    "buffalo": "Buffalo",
    "charlotte": "Charlotte",
    "chicago": "Chicago",
    "cincinnati": "Cincinnati",
    "cleveland": "Cleveland",
    "columbia": "Columbia",
    "dallas": "Dallas",
    "denver": "Denver",
    "detroit": "Detroit",
    "elpaso": "El Paso",
    "honolulu": "Honolulu",
    "houston": "Houston",
    "indianapolis": "Indianapolis",
    "jackson": "Jackson",
    "jacksonville": "Jacksonville",
    "kansascity": "Kansas City",
    "knoxville": "Knoxville",
    "lasvegas": "Las Vegas",
    "littlerock": "Little Rock",
    "losangeles": "Los Angeles",
    "louisville": "Louisville",
    "memphis": "Memphis",
    "miami": "Miami",
    "milwaukee": "Milwaukee",
    "minneapolis": "Minneapolis",
    "mobile": "Mobile",
    "newhaven": "New Haven",
    "neworleans": "New Orleans",
    "newyork": "New York",
    "newark": "Newark",
    "norfolk": "Norfolk",
    "oklahomacity": "Oklahoma City",
    "omaha": "Omaha",
    "philadelphia": "Philadelphia",
    "phoenix": "Phoenix",
    "pittsburgh": "Pittsburgh",
    "portland": "Portland",
    "richmond": "Richmond",
    "sacramento": "Sacramento",
    "saltlakecity": "Salt Lake City",
    "sanantonio": "San Antonio",
    "sandiego": "San Diego",
    "sanfrancisco": "San Francisco",
    "sanjuan": "San Juan",
    "seattle": "Seattle",
    "springfield": "Springfield",
    "stlouis": "St. Louis",
    "tampa": "Tampa",
    "washingtondc": "Washington D.C.",
    "wfo": "Washington Field Office",
}

# Poster classification to readable name
POSTER_CLASSIFICATIONS = {
    "ten": "FBI Top Ten Most Wanted",
    "terrorist": "Most Wanted Terrorist",
    "missing": "Missing Person",
    "kidnapping": "Kidnapping",
    "default": "Wanted Fugitive",
    "seeking": "Seeking Information",
    "parental": "Parental Kidnapping",
    "ecap": "Endangered Child Alert",
    "law": "Law Enforcement Assistance",
    "victim": "Victim Assistance",
}


def inches_to_height_str(inches: Optional[int]) -> str:
    """
    Convert height in inches to feet'inches" format.
    
    Args:
        inches: Height in inches (e.g., 70)
        
    Returns:
        Formatted string (e.g., "5'10\"") or empty string if None
    """
    if inches is None:
        return ""
    try:
        inches = int(inches)
        feet = inches // 12
        remaining_inches = inches % 12
        return f"{feet}'{remaining_inches}\""
    except (ValueError, TypeError):
        return str(inches)


def format_field_offices(offices: Optional[List[str]]) -> str:
    """
    Convert field office codes to readable names.
    
    Args:
        offices: List of field office codes (e.g., ["losangeles", "phoenix"])
        
    Returns:
        Comma-separated readable names (e.g., "Los Angeles, Phoenix")
    """
    if not offices:
        return ""
    readable = [FIELD_OFFICES.get(office.lower(), office.title()) for office in offices]
    return ", ".join(readable)


def format_classification(classification: Optional[str]) -> str:
    """
    Convert poster classification code to readable name.
    
    Args:
        classification: Classification code (e.g., "ten")
        
    Returns:
        Readable name (e.g., "FBI Top Ten Most Wanted")
    """
    if not classification:
        return ""
    return POSTER_CLASSIFICATIONS.get(classification.lower(), classification.title())


def flatten_array(arr: Optional[List], delimiter: str = "; ") -> str:
    """
    Flatten an array to a delimited string.
    
    Args:
        arr: List of values
        delimiter: Separator string (default "; ")
        
    Returns:
        Delimited string or empty string if None
    """
    if not arr:
        return ""
    return delimiter.join(str(item) for item in arr)


def format_reward(amount: Optional[int]) -> str:
    """
    Format reward amount as currency string.
    
    Args:
        amount: Reward amount in dollars
        
    Returns:
        Formatted string (e.g., "$50,000") or empty string if None
    """
    if amount is None:
        return ""
    try:
        return f"${amount:,}"
    except (ValueError, TypeError):
        return str(amount)


def safe_get(data: Dict, key: str, default: Any = "") -> Any:
    """Safely get a value from a dict, returning default if not found or None."""
    value = data.get(key)
    return value if value is not None else default


# ============================================================================
# CSV CONVERSION
# ============================================================================

# Define the columns to export in CSV (ordered)
CSV_COLUMNS = [
    "title",
    "aliases",
    "sex",
    "race",
    "age_min",
    "age_max",
    "height_min",
    "height_max",
    "weight",
    "hair",
    "eyes",
    "build",
    "complexion",
    "scars_and_marks",
    "nationality",
    "place_of_birth",
    "languages",
    "caution",
    "warning_message",
    "reward_min",
    "reward_max",
    "reward_text",
    "description",
    "details",
    "remarks",
    "field_offices",
    "subjects",
    "poster_classification",
    "person_classification",
    "status",
    "ncic",
    "dates_of_birth_used",
    "occupations",
    "possible_countries",
    "possible_states",
    "locations",
    "modified",
    "publication",
    "url",
    "path",
    "pathid",
]


def convert_to_csv(result_dict: Dict) -> str:
    """
    Convert search results to CSV format.
    
    Args:
        result_dict: The search result dictionary containing 'items'
        
    Returns:
        CSV formatted string
    """
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_MINIMAL)
    
    # Write header row
    writer.writerow(CSV_COLUMNS)
    
    # Write data rows
    items = result_dict.get("items", [])
    for item in items:
        data = item.get("data", {})
        row = []
        for col in CSV_COLUMNS:
            value = safe_get(data, col, "")
            
            # Flatten arrays to semicolon-delimited strings
            if isinstance(value, list):
                value = flatten_array(value)
            
            row.append(value)
        
        writer.writerow(row)
    
    return output.getvalue()


# ============================================================================
# TXT (Plain Text BOLO Format) CONVERSION
# ============================================================================

def convert_to_txt(result_dict: Dict) -> str:
    """
    Convert search results to human-readable plain text BOLO format.
    
    Args:
        result_dict: The search result dictionary containing 'items'
        
    Returns:
        Plain text formatted string
    """
    lines = []
    
    # Header
    lines.append("=" * 80)
    lines.append("                          FBI WANTED PERSONS SEARCH RESULTS")
    lines.append("=" * 80)
    
    # Query info
    query = result_dict.get("query", {})
    endpoint = query.get("endpoint", "search")
    count = result_dict.get("resultcount", 0)
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    lines.append(f"Query: {endpoint} | Results: {count} | Generated: {timestamp}")
    lines.append("=" * 80)
    lines.append("")
    
    # Process each item
    items = result_dict.get("items", [])
    for idx, item in enumerate(items, 1):
        data = item.get("data", {})
        
        lines.append("-" * 80)
        lines.append(f"RECORD {idx} of {count}")
        lines.append("-" * 80)
        
        # Name and aliases
        title = safe_get(data, "title", "UNKNOWN")
        lines.append(f"NAME:               {title}")
        
        aliases = safe_get(data, "aliases", [])
        if aliases:
            lines.append(f"ALIASES:            {flatten_array(aliases, ', ')}")
        
        # Classification
        classification = safe_get(data, "poster_classification", "")
        if classification:
            readable_class = format_classification(classification)
            lines.append(f"CLASSIFICATION:     {readable_class}")
        
        lines.append("")
        lines.append("DESCRIPTION:")
        
        # Physical description
        sex = safe_get(data, "sex", "")
        if sex:
            lines.append(f"  Sex:              {sex}")
        
        race = safe_get(data, "race", "")
        if race:
            lines.append(f"  Race:             {race}")
        
        age_min = safe_get(data, "age_min")
        age_max = safe_get(data, "age_max")
        if age_min or age_max:
            if age_min and age_max:
                lines.append(f"  Age:              {age_min} - {age_max}")
            elif age_min:
                lines.append(f"  Age:              {age_min}+")
            else:
                lines.append(f"  Age:              Up to {age_max}")
        
        height_min = safe_get(data, "height_min")
        height_max = safe_get(data, "height_max")
        if height_min or height_max:
            h_min_str = inches_to_height_str(height_min)
            h_max_str = inches_to_height_str(height_max)
            if height_min and height_max:
                lines.append(f"  Height:           {h_min_str} - {h_max_str} ({height_min} - {height_max} inches)")
            elif height_min:
                lines.append(f"  Height:           {h_min_str}+ ({height_min}+ inches)")
            else:
                lines.append(f"  Height:           Up to {h_max_str} ({height_max} inches)")
        
        weight = safe_get(data, "weight", "")
        if weight:
            lines.append(f"  Weight:           {weight}")
        
        hair = safe_get(data, "hair", "")
        if hair:
            lines.append(f"  Hair:             {hair}")
        
        eyes = safe_get(data, "eyes", "")
        if eyes:
            lines.append(f"  Eyes:             {eyes}")
        
        build = safe_get(data, "build", "")
        if build:
            lines.append(f"  Build:            {build}")
        
        complexion = safe_get(data, "complexion", "")
        if complexion:
            lines.append(f"  Complexion:       {complexion}")
        
        nationality = safe_get(data, "nationality", "")
        if nationality:
            lines.append(f"  Nationality:      {nationality}")
        
        pob = safe_get(data, "place_of_birth", "")
        if pob:
            lines.append(f"  Place of Birth:   {pob}")
        
        languages = safe_get(data, "languages", [])
        if languages:
            lines.append(f"  Languages:        {flatten_array(languages, ', ')}")
        
        lines.append("")
        
        # Scars and marks
        scars = safe_get(data, "scars_and_marks", "")
        if scars:
            lines.append(f"SCARS/MARKS:        {scars}")
            lines.append("")
        
        # Caution
        caution = safe_get(data, "caution", "")
        if caution:
            # Clean up HTML if present
            caution = caution.replace("<p>", "").replace("</p>", " ").strip()
            lines.append(f"CAUTION:            {caution}")
            lines.append("")
        
        warning = safe_get(data, "warning_message", "")
        if warning:
            lines.append(f"WARNING:            {warning}")
            lines.append("")
        
        # Reward
        reward_max = safe_get(data, "reward_max")
        reward_text = safe_get(data, "reward_text", "")
        if reward_max:
            lines.append(f"REWARD:             {format_reward(reward_max)}")
            if reward_text:
                lines.append(f"                    {reward_text}")
            lines.append("")
        
        # Description/Details
        description = safe_get(data, "description", "")
        if description:
            lines.append(f"OFFENSE:            {description}")
            lines.append("")
        
        details = safe_get(data, "details", "")
        if details:
            # Clean up HTML
            details = details.replace("<p>", "").replace("</p>", "\n").strip()
            lines.append("DETAILS:")
            for detail_line in details.split("\n"):
                if detail_line.strip():
                    lines.append(f"  {detail_line.strip()}")
            lines.append("")
        
        # Subjects/Categories
        subjects = safe_get(data, "subjects", [])
        if subjects:
            lines.append(f"SUBJECTS:           {flatten_array(subjects, ', ')}")
        
        # Field offices
        field_offices = safe_get(data, "field_offices", [])
        if field_offices:
            lines.append(f"FIELD OFFICES:      {format_field_offices(field_offices)}")
        
        # Dates
        modified = safe_get(data, "modified", "")
        if modified:
            lines.append(f"LAST MODIFIED:      {modified}")
        
        # URL
        url = safe_get(data, "url", "")
        if url:
            lines.append(f"FBI URL:            {url}")
        
        # NCIC
        ncic = safe_get(data, "ncic", "")
        if ncic:
            lines.append(f"NCIC:               {ncic}")
        
        lines.append("")
    
    # Footer
    lines.append("=" * 80)
    lines.append("                              END OF SEARCH RESULTS")
    lines.append("=" * 80)
    
    return "\n".join(lines)


# ============================================================================
# XML CONVERSION
# ============================================================================

def escape_xml(value: Any) -> str:
    """Escape special XML characters."""
    if value is None:
        return ""
    s = str(value)
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;")
    s = s.replace(">", "&gt;")
    s = s.replace('"', "&quot;")
    s = s.replace("'", "&apos;")
    return s


def convert_to_xml(result_dict: Dict) -> str:
    """
    Convert search results to XML format.
    
    Args:
        result_dict: The search result dictionary containing 'items'
        
    Returns:
        XML formatted string
    """
    lines = []
    
    # XML declaration and root element
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f'<FBIWantedSearchResults xmlns="http://www.fbi.gov/wanted/schema/v1" generated="{timestamp}">')
    
    # Query info
    query = result_dict.get("query", {})
    role = result_dict.get("role", "")
    count = result_dict.get("resultcount", 0)
    
    lines.append("  <QueryInfo>")
    
    endpoint = query.get("endpoint", "")
    if endpoint:
        lines.append(f"    <Endpoint>{escape_xml(endpoint)}</Endpoint>")
    
    if role:
        lines.append(f"    <Role>{escape_xml(role)}</Role>")
    
    lines.append(f"    <ResultCount>{count}</ResultCount>")
    lines.append("  </QueryInfo>")
    
    # Wanted persons
    lines.append("  <WantedPersons>")
    
    items = result_dict.get("items", [])
    for idx, item in enumerate(items, 1):
        data = item.get("data", {})
        data_type = item.get("data_type", "raw")
        
        lines.append(f'    <WantedPerson sequence="{idx}" dataType="{data_type}">')
        
        # Name
        title = safe_get(data, "title", "")
        if title:
            lines.append(f"      <Name>{escape_xml(title)}</Name>")
        
        # Aliases (array)
        aliases = safe_get(data, "aliases", [])
        if aliases:
            lines.append("      <Aliases>")
            for alias in aliases:
                lines.append(f"        <Alias>{escape_xml(alias)}</Alias>")
            lines.append("      </Aliases>")
        
        # Classification
        classification = safe_get(data, "poster_classification", "")
        if classification:
            lines.append(f"      <PosterClassification>{escape_xml(classification)}</PosterClassification>")
        
        person_class = safe_get(data, "person_classification", "")
        if person_class:
            lines.append(f"      <PersonClassification>{escape_xml(person_class)}</PersonClassification>")
        
        # Physical description
        lines.append("      <PhysicalDescription>")
        
        for field in ["sex", "race", "nationality", "place_of_birth"]:
            value = safe_get(data, field, "")
            if value:
                tag = "".join(word.capitalize() for word in field.split("_"))
                lines.append(f"        <{tag}>{escape_xml(value)}</{tag}>")
        
        for field in ["age_min", "age_max", "height_min", "height_max"]:
            value = safe_get(data, field)
            if value is not None:
                tag = "".join(word.capitalize() for word in field.split("_"))
                lines.append(f"        <{tag}>{value}</{tag}>")
        
        weight = safe_get(data, "weight", "")
        if weight:
            lines.append(f"        <Weight>{escape_xml(weight)}</Weight>")
        
        for field in ["hair", "eyes", "build", "complexion"]:
            value = safe_get(data, field, "")
            if value:
                tag = field.capitalize()
                lines.append(f"        <{tag}>{escape_xml(value)}</{tag}>")
        
        lines.append("      </PhysicalDescription>")
        
        # Languages (array)
        languages = safe_get(data, "languages", [])
        if languages:
            lines.append("      <Languages>")
            for lang in languages:
                lines.append(f"        <Language>{escape_xml(lang)}</Language>")
            lines.append("      </Languages>")
        
        # Scars and marks
        scars = safe_get(data, "scars_and_marks", "")
        if scars:
            lines.append(f"      <ScarsAndMarks>{escape_xml(scars)}</ScarsAndMarks>")
        
        # Caution and warning
        caution = safe_get(data, "caution", "")
        if caution:
            # Clean up HTML
            caution = caution.replace("<p>", "").replace("</p>", " ").strip()
            lines.append(f"      <CautionStatement>{escape_xml(caution)}</CautionStatement>")
        
        warning = safe_get(data, "warning_message", "")
        if warning:
            lines.append(f"      <WarningMessage>{escape_xml(warning)}</WarningMessage>")
        
        # Reward
        reward_min = safe_get(data, "reward_min")
        reward_max = safe_get(data, "reward_max")
        reward_text = safe_get(data, "reward_text", "")
        if reward_min is not None or reward_max is not None or reward_text:
            lines.append('      <Reward currency="USD">')
            if reward_min is not None:
                lines.append(f"        <MinAmount>{reward_min}</MinAmount>")
            if reward_max is not None:
                lines.append(f"        <MaxAmount>{reward_max}</MaxAmount>")
            if reward_text:
                lines.append(f"        <Text>{escape_xml(reward_text)}</Text>")
            lines.append("      </Reward>")
        
        # Description and details
        description = safe_get(data, "description", "")
        if description:
            lines.append(f"      <Description>{escape_xml(description)}</Description>")
        
        details = safe_get(data, "details", "")
        if details:
            lines.append(f"      <Details>{escape_xml(details)}</Details>")
        
        remarks = safe_get(data, "remarks", "")
        if remarks:
            lines.append(f"      <Remarks>{escape_xml(remarks)}</Remarks>")
        
        # Subjects (array)
        subjects = safe_get(data, "subjects", [])
        if subjects:
            lines.append("      <Subjects>")
            for subject in subjects:
                lines.append(f"        <Subject>{escape_xml(subject)}</Subject>")
            lines.append("      </Subjects>")
        
        # Field offices (array)
        field_offices = safe_get(data, "field_offices", [])
        if field_offices:
            lines.append("      <FieldOffices>")
            for office in field_offices:
                lines.append(f"        <FieldOffice>{escape_xml(office)}</FieldOffice>")
            lines.append("      </FieldOffices>")
        
        # Locations (array)
        locations = safe_get(data, "locations", [])
        if locations:
            lines.append("      <Locations>")
            for loc in locations:
                lines.append(f"        <Location>{escape_xml(loc)}</Location>")
            lines.append("      </Locations>")
        
        # Possible countries/states (arrays)
        countries = safe_get(data, "possible_countries", [])
        if countries:
            lines.append("      <PossibleCountries>")
            for country in countries:
                lines.append(f"        <Country>{escape_xml(country)}</Country>")
            lines.append("      </PossibleCountries>")
        
        states = safe_get(data, "possible_states", [])
        if states:
            lines.append("      <PossibleStates>")
            for state in states:
                lines.append(f"        <State>{escape_xml(state)}</State>")
            lines.append("      </PossibleStates>")
        
        # Occupations (array)
        occupations = safe_get(data, "occupations", [])
        if occupations:
            lines.append("      <Occupations>")
            for occ in occupations:
                lines.append(f"        <Occupation>{escape_xml(occ)}</Occupation>")
            lines.append("      </Occupations>")
        
        # Dates of birth used (array)
        dobs = safe_get(data, "dates_of_birth_used", [])
        if dobs:
            lines.append("      <DatesOfBirthUsed>")
            for dob in dobs:
                lines.append(f"        <DateOfBirth>{escape_xml(dob)}</DateOfBirth>")
            lines.append("      </DatesOfBirthUsed>")
        
        # Status and NCIC
        status = safe_get(data, "status", "")
        if status:
            lines.append(f"      <Status>{escape_xml(status)}</Status>")
        
        ncic = safe_get(data, "ncic", "")
        if ncic:
            lines.append(f"      <NCIC>{escape_xml(ncic)}</NCIC>")
        
        # Dates
        modified = safe_get(data, "modified", "")
        if modified:
            lines.append(f"      <ModifiedDate>{escape_xml(modified)}</ModifiedDate>")
        
        publication = safe_get(data, "publication", "")
        if publication:
            lines.append(f"      <PublicationDate>{escape_xml(publication)}</PublicationDate>")
        
        # URLs
        url = safe_get(data, "url", "")
        if url:
            lines.append(f"      <FBIUrl>{escape_xml(url)}</FBIUrl>")
        
        path = safe_get(data, "path", "")
        if path:
            lines.append(f"      <Path>{escape_xml(path)}</Path>")
        
        pathid = safe_get(data, "pathid", "")
        if pathid:
            lines.append(f"      <PathId>{escape_xml(pathid)}</PathId>")
        
        lines.append("    </WantedPerson>")
    
    lines.append("  </WantedPersons>")
    lines.append("</FBIWantedSearchResults>")
    
    return "\n".join(lines)


# ============================================================================
# PARQUET CONVERSION
# ============================================================================

def convert_to_parquet(result_dict: Dict) -> bytes:
    """
    Convert search results to Apache Parquet format.
    
    Parquet is a columnar storage format optimized for analytics:
    - 70-90% smaller than CSV
    - Preserves data types (integers, strings, arrays)
    - Native support in pandas, polars, DuckDB, Spark, Arrow
    - Standard format for modern data pipelines
    
    Args:
        result_dict: The search result dictionary containing:
            - items: List of wrapped wanted person records (each with data_type and data fields)
            - query: Search parameters used
            - resultcount: Total matching records
            - role: User role
            
    Returns:
        Bytes of the Parquet file
        
    Example usage:
        # In Python
        import pandas as pd
        df = pd.read_parquet('results.parquet')
        
        # In DuckDB
        SELECT * FROM 'results.parquet' WHERE reward_min > 10000;
    """
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as e:
        raise ImportError(f"PyArrow is required for Parquet format. Install with: pip install pyarrow. Error: {str(e)}")
    
    # Extract actual records from items[].data structure
    items = result_dict.get("items", [])
    results = [item.get("data", {}) for item in items] if items else []
    
    # Define all possible fields and their types
    # Scalars (simple types)
    scalar_fields = [
        'uid', 'title', 'sex', 'race', 'nationality', 'place_of_birth',
        'age_min', 'age_max', 'height_min', 'height_max', 'weight',
        'hair', 'eyes', 'build', 'complexion', 'scars_and_marks',
        'caution', 'warning_message', 'description', 'details', 'remarks',
        'reward_min', 'reward_max', 'reward_text', 'status', 'ncic',
        'modified', 'publication', 'url', 'path', 'pathid',
        'person_classification', 'poster_classification'
    ]
    
    # Array fields (list types)
    array_fields = [
        'aliases', 'languages', 'subjects', 'field_offices', 'locations',
        'possible_countries', 'possible_states', 'occupations', 'dates_of_birth_used',
        'images', 'files'
    ]
    
    # Define schema once (used for both empty and populated tables)
    schema = pa.schema([
        # Identifiers
        ('uid', pa.string()),
        ('title', pa.string()),
        
        # Demographics
        ('sex', pa.string()),
        ('race', pa.string()),
        ('nationality', pa.string()),
        ('place_of_birth', pa.string()),
        
        # Physical measurements (integers where applicable)
        ('age_min', pa.int32()),
        ('age_max', pa.int32()),
        ('height_min', pa.int32()),
        ('height_max', pa.int32()),
        ('weight', pa.string()),  # Can contain ranges like "150-170"
        
        # Physical description
        ('hair', pa.string()),
        ('eyes', pa.string()),
        ('build', pa.string()),
        ('complexion', pa.string()),
        ('scars_and_marks', pa.string()),
        
        # Arrays (list types)
        ('aliases', pa.list_(pa.string())),
        ('languages', pa.list_(pa.string())),
        
        # Case information
        ('caution', pa.string()),
        ('warning_message', pa.string()),
        ('description', pa.string()),
        ('details', pa.string()),
        ('remarks', pa.string()),
        
        # Categories and subjects
        ('subjects', pa.list_(pa.string())),
        ('person_classification', pa.string()),
        ('poster_classification', pa.string()),
        
        # Reward information
        ('reward_min', pa.int64()),
        ('reward_max', pa.int64()),
        ('reward_text', pa.string()),
        
        # Geographic information
        ('field_offices', pa.list_(pa.string())),
        ('locations', pa.list_(pa.string())),
        ('possible_countries', pa.list_(pa.string())),
        ('possible_states', pa.list_(pa.string())),
        
        # Additional details
        ('occupations', pa.list_(pa.string())),
        ('dates_of_birth_used', pa.list_(pa.string())),
        
        # Status
        ('status', pa.string()),
        ('ncic', pa.string()),
        
        # Dates
        ('modified', pa.string()),  # ISO format strings
        ('publication', pa.string()),
        
        # URLs and media
        ('url', pa.string()),
        ('path', pa.string()),
        ('pathid', pa.string()),
        ('images', pa.list_(pa.string())),
        ('files', pa.list_(pa.string()))
    ])
    
    if not results:
        # Create empty table with all schema fields as empty arrays
        data_dict = {}
        for field in scalar_fields:
            data_dict[field] = []
        for field in array_fields:
            data_dict[field] = []
        table = pa.Table.from_pydict(data_dict, schema=schema)
    else:
        # Convert results to columnar format
        # Flatten the data structure for Parquet while preserving types
        data_dict = {}
        
        # Initialize columns
        for field in scalar_fields:
            data_dict[field] = []
        for field in array_fields:
            data_dict[field] = []
        
        # Populate columns from results
        for record in results:
            # Scalar fields
            for field in scalar_fields:
                value = record.get(field)
                # Handle None vs empty string appropriately
                if field in ['age_min', 'age_max', 'height_min', 'height_max', 'reward_min', 'reward_max']:
                    # Keep None for numeric fields, convert non-numeric to None
                    if value is None:
                        data_dict[field].append(None)
                    elif isinstance(value, (int, float)):
                        data_dict[field].append(int(value) if not isinstance(value, bool) else None)
                    else:
                        # Can't convert to int, store None
                        data_dict[field].append(None)
                else:
                    # Convert to string, handling dicts/objects
                    if value is None:
                        data_dict[field].append('')
                    elif isinstance(value, (dict, list)):
                        # Convert complex types to JSON string
                        data_dict[field].append(json.dumps(value))
                    else:
                        data_dict[field].append(str(value))
            
            # Array fields - store as lists (Parquet supports list types)
            for field in array_fields:
                value = record.get(field)
                # Ensure it's a list (or None)
                if value is None or (isinstance(value, list) and len(value) == 0):
                    data_dict[field].append(None)
                elif isinstance(value, list):
                    # Convert all list items to strings to be safe
                    data_dict[field].append([str(item) if item is not None else '' for item in value])
                else:
                    # Single value - convert to list with string
                    data_dict[field].append([str(value)])
        
        # Create PyArrow table with the schema defined above
        table = pa.Table.from_pydict(data_dict, schema=schema)
    
    # Write to bytes buffer using BytesIO
    buffer = io.BytesIO()
    pq.write_table(
        table, 
        buffer,
        compression='snappy',  # Good balance of speed and compression
        write_statistics=True   # Include statistics for query optimization
    )
    
    # Get bytes and return
    buffer.seek(0)
    return buffer.read()


# ============================================================================
# MAIN FORMAT RESPONSE FUNCTION
# ============================================================================

def format_response(
    result_dict: Dict,
    response_format: ResponseFormat,
    filename_prefix: str = "bolo_results"
) -> Response:
    """
    Format the search result based on the requested format.
    
    Args:
        result_dict: The search result dictionary
        response_format: The desired output format (JSON, CSV, TXT, XML, Parquet)
        filename_prefix: Prefix for the download filename
        
    Returns:
        FastAPI Response object with appropriate content and headers
    """
    # JSON - return the dict directly (FastAPI will serialize it)
    if response_format == ResponseFormat.JSON:
        return result_dict
    
    # Generate timestamp for filename
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    # CSV
    if response_format == ResponseFormat.CSV:
        content = convert_to_csv(result_dict)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename={filename_prefix}_{timestamp}.csv"
            }
        )
    
    # TXT (Plain text)
    if response_format == ResponseFormat.TXT:
        content = convert_to_txt(result_dict)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f"attachment; filename={filename_prefix}_{timestamp}.txt"
            }
        )
    
    # XML
    if response_format == ResponseFormat.XML:
        content = convert_to_xml(result_dict)
        return Response(
            content=content,
            media_type="application/xml",
            headers={
                "Content-Disposition": f"attachment; filename={filename_prefix}_{timestamp}.xml"
            }
        )
    
    # Parquet
    if response_format == ResponseFormat.PARQUET:
        try:
            content = convert_to_parquet(result_dict)
            if not isinstance(content, bytes):
                raise ValueError(f"convert_to_parquet returned {type(content).__name__} instead of bytes")
            return Response(
                content=content,
                media_type="application/vnd.apache.parquet",
                headers={
                    "Content-Disposition": f"attachment; filename={filename_prefix}_{timestamp}.parquet"
                }
            )
        except Exception as e:
            # Log the full error and re-raise
            import traceback
            error_detail = f"Parquet conversion error: {str(e)}\n{traceback.format_exc()}"
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=error_detail
            )
    
    # Default fallback to JSON (shouldn't reach here)
    return result_dict
