import logging
import psycopg2
import re
from dbconfig import DB_CONFIG
from lookups import COUNTRIES, STATES
from psycopg2.extensions import connection as Connection
from psycopg2.extras import RealDictCursor
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator 
from typing import List, Literal, Union, Any, Dict
from enum import Enum
from datetime import datetime
from contextlib import contextmanager

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI Router
router = APIRouter(prefix="/api/search", tags=["Search features"])

class FieldDataType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    TIMESTAMP = "timestamp"
    JSONB = "jsonb"
    TEXT_ARRAY = "text_array"

class FieldTypeMap:
    """Maps searchable fields to their PostgreSQL data types"""
    
    FIELD_TYPES: Dict[str, FieldDataType] = {
        # Integer fields
        "age_max": FieldDataType.INTEGER,
        "age_min": FieldDataType.INTEGER,
        "height_max": FieldDataType.INTEGER,
        "height_min": FieldDataType.INTEGER,
        "reward_max": FieldDataType.INTEGER,
        "reward_min": FieldDataType.INTEGER,
        "weight_max": FieldDataType.INTEGER,
        "weight_min": FieldDataType.INTEGER,
        
        # Timestamp fields
        "modified": FieldDataType.TIMESTAMP,
        "publication": FieldDataType.TIMESTAMP,
        
        # JSONB fields
        "coordinates": FieldDataType.JSONB,
        
        # Text array fields (text[][])
        "aliases": FieldDataType.TEXT_ARRAY,
        "dates_of_birth_used": FieldDataType.TEXT_ARRAY,
        "field_offices": FieldDataType.TEXT_ARRAY,
        "languages": FieldDataType.TEXT_ARRAY,
        "legat_names": FieldDataType.TEXT_ARRAY,
        "locations": FieldDataType.TEXT_ARRAY,
        "occupations": FieldDataType.TEXT_ARRAY,
        "possible_countries": FieldDataType.TEXT_ARRAY,
        "possible_states": FieldDataType.TEXT_ARRAY,
        "subjects": FieldDataType.TEXT_ARRAY,
        "suspects": FieldDataType.TEXT_ARRAY,
        
        # String/text fields
        "build": FieldDataType.STRING,
        "caution": FieldDataType.STRING,
        "complexion": FieldDataType.STRING,
        "description": FieldDataType.STRING,
        "details": FieldDataType.STRING,
        "eyes": FieldDataType.STRING,
        "eyes_raw": FieldDataType.STRING,
        "hair": FieldDataType.STRING,
        "hair_raw": FieldDataType.STRING,
        "nationality": FieldDataType.STRING,
        "ncic": FieldDataType.STRING,
        "path": FieldDataType.STRING,
        "pathid": FieldDataType.STRING,
        "person_classification": FieldDataType.STRING,
        "place_of_birth": FieldDataType.STRING,
        "poster_classification": FieldDataType.STRING,
        "poster_url": FieldDataType.STRING,
        "race": FieldDataType.STRING,
        "race_raw": FieldDataType.STRING,
        "remarks": FieldDataType.STRING,
        "reward_text": FieldDataType.STRING,
        "scars_and_marks": FieldDataType.STRING,
        "sex": FieldDataType.STRING,
        "status": FieldDataType.STRING,
        "title": FieldDataType.STRING,
        "url": FieldDataType.STRING,
        "warning_message": FieldDataType.STRING,
        "weight": FieldDataType.STRING,
    }
    
    @classmethod
    def is_string_field(cls, field: str) -> bool:
        """Check if a field is a string/text type"""
        return cls.FIELD_TYPES.get(field) == FieldDataType.STRING
    
    @classmethod
    def get_type(cls, field: str) -> FieldDataType:
        """Get the data type for a field"""
        return cls.FIELD_TYPES.get(field, FieldDataType.STRING)

class LogicOperator(str, Enum):
    """Logical operators for combining conditions"""
    AND = "AND"
    OR = "OR"

class ComparisonOperator(str, Enum):
    """
    Available comparison operators:
    - equals: Exact match
    - contains: Field contains value (case-insensitive)
    - starts_with: Field starts with value (case-insensitive)
    - ends_with: Field ends with value (case-insensitive)
    - gt: Greater than (numeric/date fields)
    - lt: Less than (numeric/date fields)
    - gte: Greater than or equal (numeric/date fields)
    - lte: Less than or equal (numeric/date fields)
    - between: Between two values (numeric/date fields)
    """
    equals = "equals"
    contains = "contains"
    starts_with = "starts_with"
    ends_with = "ends_with"
    gt = "gt"
    lt = "lt"
    gte = "gte"
    lte = "lte"
    between = "between"

class AllowedField(str, Enum):
    """Fields available for searching"""
    age_max = "age_max"
    age_min = "age_min"
    aliases = "aliases"
    build = "build"
    caution = "caution"
    complexion = "complexion"
    coordinates = "coordinates"
    dates_of_birth_used = "dates_of_birth_used"
    description = "description"
    details = "details"
    eyes = "eyes"
    eyes_raw = "eyes_raw"
    field_offices = "field_offices"
    first_seen_date = "first_seen_date"
    full_data = "full_data"
    hair = "hair"
    hair_raw = "hair_raw"
    height_max = "height_max"
    height_min = "height_min"
    languages = "languages"
    last_seen_date = "last_seen_date"
    legat_names = "legat_names"
    locations = "locations"
    modified = "modified"
    nationality = "nationality"
    ncic = "ncic"
    occupations = "occupations"
    path = "path"
    pathid = "pathid"
    person_classification = "person_classification"
    place_of_birth = "place_of_birth"
    possible_countries = "possible_countries"
    possible_states = "possible_states"
    poster_classification = "poster_classification"
    poster_url = "poster_url"
    publication = "publication"
    race = "race"
    race_raw = "race_raw"
    remarks = "remarks"
    reward_max = "reward_max"
    reward_min = "reward_min"
    reward_text = "reward_text"
    scars_and_marks = "scars_and_marks"
    sex = "sex"
    status = "status"
    subjects = "subjects"
    suspects = "suspects"
    title = "title"
    # uid = "uid"
    url = "url"
    warning_message = "warning_message"
    weight = "weight"
    weight_max = "weight_max"
    weight_min = "weight_min"

class FilterRule(BaseModel):
    """
    A single filter rule for advanced search.
    
    Attributes:
        field: The database column to filter on
        operator: The comparison operator to use
        value: The value(s) to compare against
    
    Examples:
        - {"field": "title", "operator": "contains", "value": "Python"}
        - {"field": "age_min", "operator": "gte", "value": 25}
        - {"field": "reward_max", "operator": "between", "value": [5000, 50000]}
    """
    field: AllowedField = Field(..., description="Database column to filter on")
    operator: ComparisonOperator = Field(..., description="Comparison operator")
    value: Union[str, int, float, datetime, List[Union[str, int, float, datetime]]] = Field(
        ..., 
        description="Value to compare. For 'between' operator, provide a list of 2 values [min, max]"
    )
    
    @field_validator('value')
    @classmethod
    def validate_value(cls, v, info):
        """Validate value based on operator and field type, and normalize special fields"""
        operator = info.data.get('operator')
        field = info.data.get('field')
        
        # Get field type if field is provided
        field_type = None
        if field:
            field_name = field.value if hasattr(field, 'value') else field
            field_type = FieldTypeMap.get_type(field_name)
            
            # SPECIAL FIELD NORMALIZATION - Apply before other validation
            if field_name in ["possible_countries", "possible_states", "field_offices"] and isinstance(v, str):
                # Normalize: lowercase, trim, remove non-alpha
                normalized = re.sub(r'[^a-z]', '', v.lower().strip())
                
                if field_name == "possible_countries":
                    # Lookup in COUNTRIES dictionary
                    if normalized in COUNTRIES:
                        v = COUNTRIES[normalized]
                    else:
                        v = normalized  # Keep normalized value if not found
                
                elif field_name == "possible_states":
                    # Lookup in STATES dictionary and prepend 'US-'
                    if normalized in STATES:
                        v = f"US-{STATES[normalized]}"
                    else:
                        v = normalized  # Keep normalized value if not found
                
                elif field_name == "field_offices":
                    # Just return the normalized value (lowercase, no non-alpha)
                    v = normalized
        
        # Validate 'between' operator requires exactly 2 values
        if operator == ComparisonOperator.between:
            if not isinstance(v, list):
                raise ValueError("'between' operator requires a list of values")
            if len(v) != 2:
                raise ValueError("'between' operator requires exactly 2 values [min, max]")
            # Ensure min < max
            if v[0] >= v[1]:
                raise ValueError("For 'between' operator, first value must be less than second value")
        
        # Validate numeric operators have numeric values
        numeric_operators = {
            ComparisonOperator.gt, ComparisonOperator.lt, 
            ComparisonOperator.gte, 
            ComparisonOperator.lte
            }
        
        if operator in numeric_operators:
            if isinstance(v, list):
                raise ValueError(f"'{operator.value}' operator requires a single value, not a list")
            
            # Check if this is a timestamp field - if so, allow date strings
            is_timestamp_field = (field_type == FieldDataType.TIMESTAMP) if field_type else False
            
            if not isinstance(v, (int, float)):
                if is_timestamp_field:
                    # For timestamp fields, validate it's a valid date string
                    try:
                        from datetime import datetime
                        # Try parsing as ISO date
                        datetime.fromisoformat(str(v))
                    except (ValueError, TypeError):
                        raise ValueError(f"'{operator.value}' operator on timestamp field requires a valid date string (YYYY-MM-DD)")
                else:
                    # For numeric fields, try to convert string to number
                    try:
                        float(v)
                    except (ValueError, TypeError):
                        raise ValueError(f"'{operator.value}' operator requires a numeric value")
        
        return v
    
    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "field": "title",
                    "operator": "contains",
                    "value": "Python"
                },
                {
                    "field": "reward_max",
                    "operator": "between",
                    "value": [5000, 50000]
                }
            ]
        }

class FilterGroup(BaseModel):
    """
    A group of filter rules combined with AND/OR logic.
    
    Attributes:
        condition: How to combine rules within this group (AND/OR)
        rules: List of filter rules in this group
    
    Example:
        {
            "condition": "AND",
            "rules": [
                {"field": "title", "operator": "contains", "value": "Murder"},
                {"field": "reward_max", "operator": "gte", "value": 10000}
            ]
        }
    """
    condition: LogicOperator = Field(..., description="How to combine rules in this group")
    rules: List[FilterRule] = Field(..., min_items=1, description="Filter rules in this group")
    

    @field_validator('rules')
    @classmethod
    def validate_rules_not_empty(cls, v):
        """Ensure at least one rule exists"""
        if not v:
            raise ValueError("Each group must contain at least one rule")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "condition": "AND",
                "rules": [
                    {"field": "title", "operator": "contains", "value": "Murder"},
                    {"field": "reward_max", "operator": "gte", "value": 10000}
                ]
            }
        }

class AdvancedSearchRequest(BaseModel):
    """
    Advanced search request with grouped conditions.
    
    Supports complex queries like:
    (title contains "Murder" AND reward_max >= 10000) 
    OR 
    (sex equals "Male" AND age_min >= 30)
    
    Attributes:
        groups: List of filter groups
        group_logic: How to combine groups (AND/OR)
        limit: Maximum number of results to return
    
    Example:
        {
            "groups": [
                {
                    "condition": "AND",
                    "rules": [
                        {"field": "title", "operator": "contains", "value": "Murder"},
                        {"field": "reward_max", "operator": "gte", "value": 10000}
                    ]
                },
                {
                    "condition": "AND",
                    "rules": [
                        {"field": "sex", "operator": "equals", "value": "Male"},
                        {"field": "age_min", "operator": "gte", "value": 30}
                    ]
                }
            ],
            "group_logic": "OR",
            "limit": 50
        }
    """
    groups: List[FilterGroup] = Field(
        ..., 
        min_items=1,
        description="List of filter groups to apply"
    )
    group_logic: LogicOperator = Field(
        default=LogicOperator.AND,
        description="How to combine multiple groups (AND/OR)"
    )
    limit: Literal[50, 100, 250, 500] = Field(
        default=50,
        description="Maximum number of results to return (default: 50)"
    )
    
    @field_validator('groups')
    @classmethod
    def validate_groups_not_empty(cls, v):
        """Ensure at least one group exists"""
        if not v:
            raise ValueError("At least one filter group is required")
        return v
        
    class Config:
        json_schema_extra = {
            "example": {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": [
                            {"field": "title", "operator": "contains", "value": "Murder"},
                            {"field": "reward_max", "operator": "gte", "value": 10000}
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        }

class SimpleFilter(BaseModel):
    """
    A simple filter with wildcard support.
    
    Wildcard patterns:
    - *text*  -> matches if field contains "text"
    - text*   -> matches if field starts with "text"
    - *text   -> matches if field ends with "text"
    - text    -> matches if field equals "text" (exact match)
    
    Attributes:
        field: Database column to search in
        value: Search value with optional wildcards
    
    Examples:
        - {"field": "title", "value": "Murder*"}      # Starts with "Murder"
        - {"field": "description", "value": "*armed*"}  # Contains "armed"
        - {"field": "sex", "value": "Male"}  # Exact match
    """
    field: AllowedField = Field(..., description="Database column to search in")
    value: str = Field(
        ..., 
        min_length=1,
        description="Search value. Use * for wildcards: *text* (contains), text* (starts), *text (ends)"
        )

    @field_validator('value')
    @classmethod
    def normalize_special_fields(cls, v, info):
        """Normalize special field values before wildcard processing"""
        field = info.data.get('field')
        
        if field and isinstance(v, str):
            field_name = field.value if hasattr(field, 'value') else field
            
            # For special fields, normalize before applying wildcards
            if field_name in ["possible_countries", "possible_states", "field_offices"]:
                # Extract the actual search value (strip wildcards temporarily)
                clean_value = v.strip('*')
                
                # Normalize: lowercase, trim, remove non-alpha
                normalized = re.sub(r'[^a-z]', '', clean_value.lower().strip())
                
                # Preserve any wildcards that were present
                prefix = '*' if v.startswith('*') else ''
                suffix = '*' if v.endswith('*') else ''
                
                if field_name == "possible_countries":
                    if normalized in COUNTRIES:
                        return prefix + COUNTRIES[normalized] + suffix
                    return prefix + normalized + suffix
                
                elif field_name == "possible_states":
                    if normalized in STATES:
                        return prefix + f"US-{STATES[normalized]}" + suffix
                    return prefix + normalized + suffix
                
                elif field_name == "field_offices":
                    return prefix + normalized + suffix
        
        return v

    @field_validator('value')
    @classmethod
    def validate_wildcard_pattern(cls, v):
        """Validate wildcard patterns"""
        # Ensure value is not just wildcards
        clean_value = v.strip('*')
        if not clean_value:
            raise ValueError("Search value cannot be only wildcards. Provide at least one character to search for.")
        
        # Validate no wildcards in the middle
        if '*' in clean_value:
            raise ValueError("Wildcards (*) can only be at the beginning and/or end of the search value")
        
        return v
    
    class Config:
        json_schema_extra = {
            "examples": [
                {"field": "title", "value": "Murder*"},
                {"field": "description", "value": "*armed*"},
                {"field": "sex", "value": "Male"}
            ]
        }

class SimpleSearchRequest(BaseModel):
    """
    Simple search request using wildcard patterns.
    
    Perfect for basic searches where you want to find records matching
    text patterns without complex boolean logic.
    
    Attributes:
        filters: List of simple filters to apply
        logic: How to combine filters (AND/OR)
        limit: Maximum number of results to return
        rules: implicitly or explictly apply wildcards
    
    Example:
        {
            "filters": [
                {"field": "title", "value": "person*"},
                {"field": "description", "value": "*tutorial*"}
            ],
            "logic": "AND",
            "limit": 50, 
            "rules" :"strict"
        }
    
    This searches for records where title starts with "person" 
    AND description contains "tutorial"
    """
    filters: List[SimpleFilter] = Field(
        ...,
        min_items=1,
        description="List of filters to apply"
        )
    logic: LogicOperator = Field(
        default=LogicOperator.AND,
        description="How to combine filters (AND/OR)"
        )
    limit: Literal[50, 100, 250, 500] = Field(
        default=50,
        description="Maximum number of results to return (default: 50)"
        )
    rules: Literal["strict", "flex"] = "strict" 
    
    @field_validator('filters')
    @classmethod
    def validate_filters_not_empty(cls, v):
        """Ensure at least one filter exists"""
        if not v:
            raise ValueError("At least one filter is required")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "filters": [
                    {"field": "title", "value": "Murder*"},
                    {"field": "description", "value": "*armed*"}
                ],
                "logic": "AND",
                "limit": 50
            }
        }

def escape_sql_value(value: Any) -> str:
    """
    Escape values for SQL to prevent injection.
    Uses PostgreSQL's quote_literal equivalent.
    """
    if value is None:
        return "NULL"
    
    # Convert to string and escape single quotes
    str_value = str(value)
    escaped = str_value.replace("'", "''")
    return f"'{escaped}'"

def build_comparison_clause(field: str, operator: str, value: Union[str, int, float, List], param_placeholder: str) -> tuple:
    """
    Build a SQL WHERE clause with parameter placeholders.
    Returns tuple of (clause, params_list) for parameterized queries.
    
    Args:
        field: The database field name
        operator: The comparison operator (equals, contains, gt, lt, etc.)
        value: The value(s) to compare against
        param_placeholder: The parameter placeholder (always '%s' for psycopg2)
    
    Returns:
        tuple: (sql_clause_string, list_of_parameter_values)
    """
    # Get field data type
    field_type = FieldTypeMap.get_type(field)
    is_string = field_type == FieldDataType.STRING
    is_text_array = field_type == FieldDataType.TEXT_ARRAY
    is_integer = field_type == FieldDataType.INTEGER
    is_timestamp = field_type == FieldDataType.TIMESTAMP
    
    # Handle TEXT_ARRAY fields specially (case-insensitive)
    if is_text_array:
        if operator in ['contains', 'equals']:
            # Use ILIKE with ANY for case-insensitive matching in arrays
            return (f"EXISTS (SELECT 1 FROM unnest({field}) elem WHERE elem ILIKE {param_placeholder})", [value])
        elif operator == 'starts_with':
            return (f"EXISTS (SELECT 1 FROM unnest({field}) elem WHERE elem ILIKE {param_placeholder})", [f"{value}%"])
        elif operator == 'ends_with':
            return (f"EXISTS (SELECT 1 FROM unnest({field}) elem WHERE elem ILIKE {param_placeholder})", [f"%{value}"])
    
    # Handle string comparison operators
    if operator == 'contains':
        if is_string:
            return (f"full_data->>'{field}' ILIKE {param_placeholder}", [f"%{value}%"])
        else:
            return (f"full_data->>'{field}' = {param_placeholder}", [value])
    
    elif operator == 'starts_with':
        if is_string:
            return (f"full_data->>'{field}' ILIKE {param_placeholder}", [f"{value}%"])
        else:
            return (f"full_data->>'{field}' = {param_placeholder}", [value])
    
    elif operator == 'ends_with':
        if is_string:
            return (f"full_data->>'{field}' ILIKE {param_placeholder}", [f"%{value}"])
        else:
            return (f"full_data->>'{field}' = {param_placeholder}", [value])
        
    elif operator == 'equals':
        if is_string:
            return (f"LOWER(full_data->>'{field}') = LOWER({param_placeholder})", [value])
        elif is_timestamp:
            return (f"(full_data->>'{field}')::timestamp = {param_placeholder}::timestamp", [value])
        elif is_integer: 
            return (f"(full_data->>'{field}')::integer = {param_placeholder}", [value])
        else:  # For other numeric types
            return (f"(full_data->>'{field}')::numeric = {param_placeholder}", [value])
    
    # Handle numeric/timestamp comparison operators
    elif operator == 'gt':
        if is_timestamp:
            return (f"(full_data->>'{field}')::timestamp > {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"(full_data->>'{field}')::integer > {param_placeholder}", [value])
        else:
            return (f"(full_data->>'{field}')::numeric > {param_placeholder}", [value])
    
    elif operator == 'lt':
        if is_timestamp:
            return (f"(full_data->>'{field}')::timestamp < {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"(full_data->>'{field}')::integer < {param_placeholder}", [value])
        else:
            return (f"(full_data->>'{field}')::numeric < {param_placeholder}", [value])
    
    elif operator == 'gte':
        if is_timestamp:
            return (f"(full_data->>'{field}')::timestamp >= {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"(full_data->>'{field}')::integer >= {param_placeholder}", [value])
        else:
            return (f"(full_data->>'{field}')::numeric >= {param_placeholder}", [value])
    
    elif operator == 'lte':
        if is_timestamp:
            return (f"(full_data->>'{field}')::timestamp <= {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"(full_data->>'{field}')::integer <= {param_placeholder}", [value])
        else:
            return (f"(full_data->>'{field}')::numeric <= {param_placeholder}", [value])
    
    elif operator == 'between':
        # Value should be a list of [min, max]
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("'between' operator requires a list of exactly 2 values")
        
        if is_timestamp:
            # For timestamps, use < on end date + 1 day to include entire end date
            return (
                f"(full_data->>'{field}')::timestamp >= {param_placeholder}::timestamp AND (full_data->>'{field}')::timestamp < ({param_placeholder}::timestamp + INTERVAL '1 day')",
                [value[0], value[1]]
            )
        elif is_integer:
            return (
                f"(full_data->>'{field}')::integer BETWEEN {param_placeholder} AND {param_placeholder}",
                [value[0], value[1]]
            )
        else:
            return (
                f"(full_data->>'{field}')::numeric BETWEEN {param_placeholder} AND {param_placeholder}",
                [value[0], value[1]]
            )
    
    else:
        raise ValueError(f"Unsupported operator: {operator}")

         
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


@router.post(
    "/simple",
    summary="Simple Search with Wildcards",
    description="""
    Perform a simple search using wildcard patterns.
    
    **Perfect for:** Basic text searches without complex logic.
    
    **Wildcard Patterns:**
    - `*text*` → Contains "text" anywhere in the field
    - `text*` → Starts with "text"
    - `*text` → Ends with "text"
    - `text` → Exact match
    
    **Examples:**
    
    Search for titles starting with "Murder":
```json
    {
        "filters": [
            {"field": "title", "value": "Murder*"}
        ],
        "logic": "AND",
        "limit": 50, 
        "rules": "strict" 
    }
```
    
    Search for records with "armed" in description AND "dangerous" in caution:
```json
    {
        "filters": [
            {"field": "description", "value": "*armed*"},
            {"field": "caution", "value": "*dangerous*"}
        ],
        "logic": "AND",
        "limit": 100, 
        "rules": "strict" 
    }
```
    
    **Returns:** Query parameters, result count, and array of matching records (full_data)
    """,
    response_description="Query parameters, count, and array of full_data JSONB records"
)
async def simple_search(request: SimpleSearchRequest):
    """
    Execute a simple search with wildcard support.
    All string comparisons are case-insensitive.
    """

    # Build WHERE clause from validated filters
    where_clauses = []
    query_params = []
    
    for filter_item in request.filters:
        field = filter_item.field.value
        value = filter_item.value
        
        # Get field data type
        is_string = FieldTypeMap.is_string_field(field)
        
        # Apply flex rules: auto-wrap string fields with wildcards
        if request.rules == "flex" and is_string:
            if not ('*' in value):
                value = f"*{value}*"
        
        # For non-string fields, strip any wildcards
        if not is_string:
            value = value.replace('*', '')
        
        # Determine operator based on wildcard pattern
        if value.startswith('*') and value.endswith('*'):
            operator = 'contains'
            clean_value = value.strip('*')
        elif value.startswith('*'):
            operator = 'ends_with'
            clean_value = value.lstrip('*')
        elif value.endswith('*'):
            operator = 'starts_with'
            clean_value = value.rstrip('*')
        else:
            operator = 'equals'
            clean_value = value
        
        # Build the clause with parameter placeholder - now returns (clause, params)
        clause, params = build_comparison_clause(field, operator, clean_value, "%s")
        where_clauses.append(clause)
        query_params.extend(params)
    
    # Combine clauses with AND/OR
    where_clause = f" {request.logic.value} ".join(where_clauses)

    print("")
    print("WHERE clause:", where_clause)
    print("Parameters:", query_params)
    print("")

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT full_data
                    FROM vw_wanted_persons_active
                    WHERE {where_clause}
                    LIMIT %s
                """
                # Add limit to params
                query_params.append(request.limit)
                cur.execute(query, tuple(query_params))
                results = cur.fetchall()
                
        items = [row['full_data'] for row in results]
            
        return {
            "query": request.model_dump(),
            "resultcount": len(items),
            "items": items
        }
            
    except Exception as e:
        raise Exception(f"Database Error: {str(e)}")
    

@router.post(
    "/advanced",
    summary="Advanced Search with Grouped Conditions",
    description="""
    Perform advanced searches with grouped conditions and multiple operators.
    
    **Perfect for:** Complex queries with multiple conditions and grouping logic.
    
    **Available Operators:**
    - `equals`: Exact match (case-insensitive for strings)
    - `contains`: Field contains value (case-insensitive)
    - `starts_with`: Field starts with value (case-insensitive)
    - `ends_with`: Field ends with value (case-insensitive)
    - `gt`: Greater than (for numeric fields)
    - `lt`: Less than (for numeric fields)
    - `gte`: Greater than or equal (for numeric fields)
    - `lte`: Less than or equal (for numeric fields)
    - `between`: Between two values (for numeric fields) - requires array of 2 values [min, max]
    
    **Query Structure:**
    You can create multiple groups of rules, where each group's rules are combined with AND/OR,
    and then groups themselves are combined with AND/OR.
    
    **Example 1:** Simple AND query - High reward murders
```json
    {
        "groups": [
            {
                "condition": "AND",
                "rules": [
                    {"field": "title", "operator": "contains", "value": "Murder"},
                    {"field": "reward_max", "operator": "gte", "value": 100000}
                ]
            }
        ],
        "group_logic": "AND",
        "limit": 50
    }
```
    **Result:** title contains "Murder" AND reward_max >= 100000
    
    **Example 2:** Complex grouped query with numeric ranges
```json
    {
        "groups": [
            {
                "condition": "AND",
                "rules": [
                    {"field": "sex", "operator": "equals", "value": "Male"},
                    {"field": "age_min", "operator": "between", "value": [25, 45]}
                ]
            },
            {
                "condition": "AND",
                "rules": [
                    {"field": "reward_max", "operator": "gte", "value": 50000},
                    {"field": "subjects", "operator": "contains", "value": "Murder"}
                ]
            }
        ],
        "group_logic": "OR",
        "limit": 100
    }
```
    **Result:** (sex = "Male" AND age between 25-45) OR (reward >= 50000 AND subjects contains "Murder")
    
    **Example 3:** Array field search with text arrays
```json
    {
        "groups": [
            {
                "condition": "OR",
                "rules": [
                    {"field": "languages", "operator": "contains", "value": "Spanish"},
                    {"field": "languages", "operator": "contains", "value": "Portuguese"}
                ]
            }
        ],
        "group_logic": "AND",
        "limit": 50
    }
```
    **Result:** Languages include Spanish OR Portuguese
    
    **Example 4:** Multiple conditions across different field types
```json
    {
        "groups": [
            {
                "condition": "AND",
                "rules": [
                    {"field": "title", "operator": "starts_with", "value": "KIDNAPPING"},
                    {"field": "possible_states", "operator": "contains", "value": "California"},
                    {"field": "age_min", "operator": "gte", "value": 18}
                ]
            }
        ],
        "group_logic": "AND",
        "limit": 250
    }
```
    **Result:** Title starts with "KIDNAPPING" AND California in possible states AND minimum age >= 18
    
    **Returns:** Query parameters, result count, and array of matching records (full_data)
    """,
    response_description="Query parameters, count, and array of full_data JSONB records"
)
async def advanced_search(request: AdvancedSearchRequest):
    """
    Execute an advanced search with grouped conditions.
    All validation is performed by Pydantic before this function runs.
    Returns only the full_data JSONB column from matching rows.
    
    This function supports:
    - Multiple filter groups combined with AND/OR logic
    - All comparison operators (equals, contains, gt, lt, gte, lte, between, etc.)
    - String fields (case-insensitive matching)
    - Integer/numeric fields (with type casting)
    - Text array fields (languages, aliases, locations, etc.)
    - Complex nested boolean logic
    """
    
    try:
        # Build grouped WHERE clauses from validated request
        group_clauses = []
        query_params = []
        
        for group in request.groups:
            rule_clauses = []
            
            for rule in group.rules:
                field = rule.field.value
                operator = rule.operator.value
                value = rule.value
                
                # Build the comparison clause using the enhanced helper function
                # Returns (clause_string, [param_values])
                clause, params = build_comparison_clause(field, operator, value, "%s")
                rule_clauses.append(clause)
                query_params.extend(params)
            
            # Group rules with their condition (AND/OR)
            if rule_clauses:
                group_clause = f"({(' ' + group.condition.value + ' ').join(rule_clauses)})"
                group_clauses.append(group_clause)
        
        # Combine groups with group_logic (AND/OR)
        where_clause = f" {request.group_logic.value} ".join(group_clauses)
        
        # Debug logging
        print("")
        print("Advanced Search WHERE clause:", where_clause)
        print("Parameters:", query_params)
        print("")
        
        # Execute search using synchronous psycopg2 (same as simple search)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT full_data
                    FROM vw_wanted_persons_active
                    WHERE {where_clause}
                    LIMIT %s
                """
                # Add limit to params
                query_params.append(request.limit)
                
                # Execute the query with all parameters
                cur.execute(query, tuple(query_params))
                results = cur.fetchall()
        
        # Extract full_data JSONB from each row
        items = [row['full_data'] for row in results]
        
        # Construct response payload
        return {
            "query": request.model_dump(),
            "resultcount": len(items),
            "items": items
        }
    
    except Exception as e:
        logger.error(f"Advanced search error: {str(e)}")
        raise Exception(f"Search error: {str(e)}")


@router.get(
    "/",
    summary="API Information",
    description="Get information about this API and available endpoints"
)
async def root():
    """Return API information and usage guide"""
    return {
        "name": "Advanced Search API",
        "version": "1.0.0",
        "endpoints": {
            "/simple": "Simple wildcard-based search",
            "/advanced": "Advanced search with grouped conditions and numeric operators",
        },
        "searchable_fields": [
            "String fields: title, description, details, sex, race, etc.",
            "Numeric fields: age_min, age_max, height_min, reward_max, etc.",
            "Array fields: aliases, languages, locations, subjects, etc."
        ],
        "operators": {
            "text": ["equals", "contains", "starts_with", "ends_with"],
            "numeric": ["equals", "gt", "lt", "gte", "lte", "between"],
            "arrays": ["equals", "contains", "starts_with", "ends_with"]
        },
        "result_limits": [50, 100, 250, 500],
        "default_limit": 50
    }