import logging
import psycopg2
import re, time
from config import DB_CONFIG, API_APP_BASE_URL
from lookups import COUNTRIES, STATES

from psycopg2.extensions import connection as Connection
from psycopg2.extras import RealDictCursor

from fastapi import APIRouter, HTTPException, Request, Depends, Query, status
from fastapi.responses import FileResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from pydantic import BaseModel, ConfigDict, Field
from pydantic import field_validator 

from typing import List, Literal, Union, Any, Dict
from enum import Enum
from datetime import datetime
from contextlib import contextmanager

from auth import UserRole, get_data_field_for_role, validate_limit_for_role
from auth_jwt import require_jwt_role
from utils_format import ResponseFormat, ResponseFormatBasic, ResponseFormatPremium, format_response, validate_format_access
from service_link_validation import get_archive_info, get_archive_file_path
from utils_search_analytics import track_search_analytics

# Set up logging
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

rate_max = "500/minute"
limiter = Limiter(key_func=get_remote_address, default_limits=[rate_max])

# FastAPI Router
router = APIRouter(prefix="/v1/search")

# Tags for Swagger UI organization
TAG_SEARCH = "Search"
TAG_SEARCH_BY_CATEGORY = "Search By Category"
TAG_SEARCH_BY_LIST = "Search By List"
QUICKSTART_URL = "/quickstart#search_fields"
QUICKSTART_LINK = f"[Searchable Fields Reference]({QUICKSTART_URL})"

# ============================================================================
# VALIDATION HELPER FUNCTIONS
# ============================================================================

def validate_integer_value(value: Any, field_name: str) -> tuple:
    """
    Validate that a value can be converted to an integer.
    Returns (is_valid, error_message)
    """
    # CRITICAL: Check boolean FIRST before int check (bool is subclass of int)
    if isinstance(value, bool):
        return False, f"{field_name} must be an integer, not a boolean"
    
    if isinstance(value, int):
        return True, ""
    
    if isinstance(value, str):
        try:
            int(value)
            return True, ""
        except ValueError:
            return False, f"{field_name} must be a valid integer, got: '{value}'"
    
    if isinstance(value, float):
        if value.is_integer():
            return True, ""
        return False, f"{field_name} must be an integer, got float: {value}"
    
    return False, f"{field_name} must be an integer, got type: {type(value).__name__}"

def validate_timestamp_value(value: Any, field_name: str) -> tuple:
    """
    Validate that a value is a valid date in YYYY-MM-DD format.
    Returns (is_valid, error_message)
    """
    if isinstance(value, datetime):
        return True, ""
    
    if not isinstance(value, str):
        return False, f"{field_name} must be a date string in YYYY-MM-DD format, got type: {type(value).__name__}"
    
    # Check format with regex first (faster than parsing)
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', value):
        return False, f"{field_name} must be in YYYY-MM-DD format, got: '{value}'"
    
    # Try to parse the date to ensure it's valid
    try:
        datetime.strptime(value, '%Y-%m-%d')
        return True, ""
    except ValueError:
        return False, f"{field_name} is not a valid date: '{value}'"

def validate_string_value(value: Any, field_name: str) -> tuple:
    """
    Validate that a value is a string.
    Returns (is_valid, error_message)
    """
    if not isinstance(value, str):
        return False, f"{field_name} must be a string, got type: {type(value).__name__}"
    
    if len(value.strip()) == 0:
        return False, f"{field_name} cannot be empty or whitespace only"
    
    return True, ""

def validate_field_value_type_impl(field: str, value: Any, operator: str = None) -> tuple:
    """
    Validate that a value matches the expected type for a field.
    Returns (is_valid, error_message)
    
    Args:
        field: The field name
        value: The value to validate
        operator: Optional operator (for context in error messages)
    """
    field_type = FieldTypeMap.get_type(field)
    
    # For 'between' operator, validate both values in the list
    if operator == 'between':
        if not isinstance(value, list):
            return False, f"{field} with 'between' operator requires a list of 2 values"
        if len(value) != 2:
            return False, f"{field} with 'between' operator requires exactly 2 values, got {len(value)}"
        
        # Validate each value in the range
        for idx, val in enumerate(value):
            is_valid, error = validate_field_value_type_impl(field, val)
            if not is_valid:
                return False, f"{field}[{idx}] in range: {error}"
        
        # Ensure min < max
        try:
            if field_type == FieldDataType.INTEGER:
                if int(value[0]) >= int(value[1]):
                    return False, f"{field} range invalid: first value ({value[0]}) must be less than second value ({value[1]})"
            elif field_type == FieldDataType.TIMESTAMP:
                date1 = datetime.strptime(str(value[0]), '%Y-%m-%d')
                date2 = datetime.strptime(str(value[1]), '%Y-%m-%d')
                if date1 >= date2:
                    return False, f"{field} range invalid: first date ({value[0]}) must be before second date ({value[1]})"
        except Exception as e:
            return False, f"{field} range comparison failed: {str(e)}"
        
        return True, ""
    
    # Validate single values based on field type
    if field_type == FieldDataType.INTEGER:
        return validate_integer_value(value, field)
    
    elif field_type == FieldDataType.TIMESTAMP:
        return validate_timestamp_value(value, field)
    
    elif field_type == FieldDataType.STRING:
        return validate_string_value(value, field)
    
    elif field_type == FieldDataType.TEXT_ARRAY:
        # Array fields expect string values for searching
        return validate_string_value(value, field)
    
    elif field_type == FieldDataType.JSONB:
        # JSONB fields are more flexible, accept strings for now
        return validate_string_value(value, field)
    
    return True, ""


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
        "was_captured": FieldDataType.TIMESTAMP,
        
        # Text array fields (text[][])
        "aliases": FieldDataType.TEXT_ARRAY,
        "dates_of_birth_used": FieldDataType.TEXT_ARRAY,
        "field_offices": FieldDataType.TEXT_ARRAY,
        "languages": FieldDataType.TEXT_ARRAY,
        "locations": FieldDataType.TEXT_ARRAY,
        "occupations": FieldDataType.TEXT_ARRAY,
        "possible_countries": FieldDataType.TEXT_ARRAY,
        "possible_states": FieldDataType.TEXT_ARRAY,
        "subjects": FieldDataType.TEXT_ARRAY,
        
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
    dates_of_birth_used = "dates_of_birth_used"
    description = "description"
    details = "details"
    eyes = "eyes"
    eyes_raw = "eyes_raw"
    field_offices = "field_offices"
    hair = "hair"
    hair_raw = "hair_raw"
    height_max = "height_max"
    height_min = "height_min"
    languages = "languages"
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
    title = "title"
    # uid = "uid"
    url = "url"
    warning_message = "warning_message"
    was_captured = "was_captured"
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
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
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
        )
    
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
        
        # First, validate the value type matches the field type
        if field and operator:
            field_name = field.value if hasattr(field, 'value') else field
            operator_name = operator.value if hasattr(operator, 'value') else operator
            
            # Perform type validation
            is_valid, error_msg = validate_field_value_type_impl(field_name, v, operator_name)
            if not is_valid:
                raise ValueError(error_msg)
        
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

    @field_validator('operator')
    @classmethod
    def validate_operator_for_field_type(cls, v, info):
        """Validate that operator is compatible with field type"""
        field = info.data.get('field')
        
        if field:
            field_name = field.value if hasattr(field, 'value') else field
            field_type = FieldTypeMap.get_type(field_name)
            
            # String operators not allowed on numeric/timestamp fields
            string_operators = {'contains', 'starts_with', 'ends_with'}
            if v in string_operators:
                if field_type in [FieldDataType.INTEGER, FieldDataType.TIMESTAMP]:
                    raise ValueError(
                        f"Operator '{v}' cannot be used with {field_type.value} field '{field_name}'. "
                        f"Use numeric operators: equals, gt, lt, gte, lte, between"
                    )
            
            # Numeric operators not allowed on string fields
            numeric_operators = {'gt', 'lt', 'gte', 'lte', 'between'}
            if v in numeric_operators:
                if field_type == FieldDataType.STRING:
                    raise ValueError(
                        f"Operator '{v}' cannot be used with string field '{field_name}'. "
                        f"Use string operators: equals, contains, starts_with, ends_with"
                    )
        
        return v

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
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            "example": {
                "condition": "AND",
                "rules": [
                    {"field": "title", "operator": "contains", "value": "Murder"},
                    {"field": "reward_max", "operator": "gte", "value": 10000}
                    ]
                }
            }
        )
    condition: LogicOperator = Field(..., description="How to combine rules in this group")
    rules: List[FilterRule] = Field(..., min_items=1, description="Filter rules in this group")
    

    @field_validator('rules')
    @classmethod
    def validate_rules_not_empty(cls, v):
        """Ensure at least one rule exists"""
        if not v:
            raise ValueError("Each group must contain at least one rule")
        return v
    
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
            "limit": 25
        }
    """
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
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
                    "limit": 25
                }
            }
        )
    groups: List[FilterGroup] = Field(
        ..., 
        min_items=1,
        description="List of filter groups to apply"
        )
    group_logic: LogicOperator = Field(
        default=LogicOperator.AND,
        description="How to combine multiple groups (AND/OR)"
        )
    limit: Literal[25, 50, 100, 250, 500, 5000] = Field(
        default=25,
        description="Maximum number of results to return (default: 25)"
        )
    
    @field_validator('groups')
    @classmethod
    def validate_groups_not_empty(cls, v):
        """Ensure at least one group exists"""
        if not v:
            raise ValueError("At least one filter group is required")
        return v

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
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            "examples": [
                {"field": "title", "value": "Murder*"},
                {"field": "description", "value": "*armed*"},
                {"field": "sex", "value": "Male"}
                ]
            }
        )
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

    @field_validator('value')
    @classmethod
    def validate_value_type_for_field(cls, v, info):
        """Validate value type matches field requirements"""
        field = info.data.get('field')
        
        if field:
            field_name = field.value if hasattr(field, 'value') else field
            field_type = FieldTypeMap.get_type(field_name)
            
            # For integer fields, ensure value is numeric (after stripping wildcards)
            if field_type == FieldDataType.INTEGER:
                clean_value = v.strip('*')
                try:
                    int(clean_value)
                except ValueError:
                    raise ValueError(
                        f"Field '{field_name}' is an integer field. "
                        f"Value must be a valid integer, got: '{clean_value}'"
                    )
            
            # For timestamp fields, ensure value is valid date (after stripping wildcards)
            elif field_type == FieldDataType.TIMESTAMP:
                clean_value = v.strip('*')
                if not re.match(r'^\d{4}-\d{2}-\d{2}$', clean_value):
                    raise ValueError(
                        f"Field '{field_name}' is a timestamp field. "
                        f"Value must be in YYYY-MM-DD format, got: '{clean_value}'"
                    )
                try:
                    datetime.strptime(clean_value, '%Y-%m-%d')
                except ValueError:
                    raise ValueError(
                        f"Field '{field_name}' has invalid date: '{clean_value}'"
                    )
        
        return v

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
    model_config = ConfigDict(
        extra='forbid',
        json_schema_extra={
            "example": {
                "filters": [
                    {"field": "title", "value": "Murder*"},
                    {"field": "description", "value": "*armed*"}
                    ],
                "logic": "OR",
                "limit": 25
                }
            }
        )
    filters: List[SimpleFilter] = Field(
        ...,
        min_items=1,
        description="List of filters to apply"
        )
    logic: LogicOperator = Field(
        default=LogicOperator.AND,
        description="How to combine filters (AND/OR)"
        )
    limit: Literal[25, 50, 100, 250, 500, 5000] = Field(
        default=25,
        description="Maximum number of results to return (default: 25)"
        )
    rules: Literal["strict", "flex"] = "strict"
    
    @field_validator('filters')
    @classmethod
    def validate_filters_not_empty(cls, v):
        """Ensure at least one filter exists"""
        if not v:
            raise ValueError("At least one filter is required")
        return v

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
    
    Queries are built against direct columns in vw_bolo, NOT the full_data JSONB.
    
    Args:
        field: The database field name (must be a column in vw_bolo)
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
    
    # Handle string comparison operators - query direct columns in vw_bolo
    if operator == 'contains':
        if is_string:
            return (f"{field} ILIKE {param_placeholder}", [f"%{value}%"])
        else:
            return (f"{field} = {param_placeholder}", [value])
    
    elif operator == 'starts_with':
        if is_string:
            return (f"{field} ILIKE {param_placeholder}", [f"{value}%"])
        else:
            return (f"{field} = {param_placeholder}", [value])
    
    elif operator == 'ends_with':
        if is_string:
            return (f"{field} ILIKE {param_placeholder}", [f"%{value}"])
        else:
            return (f"{field} = {param_placeholder}", [value])
        
    elif operator == 'equals':
        if is_string:
            return (f"LOWER({field}) = LOWER({param_placeholder})", [value])
        elif is_timestamp:
            return (f"{field} = {param_placeholder}::timestamp", [value])
        elif is_integer: 
            return (f"{field} = {param_placeholder}", [value])
        else:  # For other numeric types
            return (f"{field} = {param_placeholder}", [value])
    
    # Handle numeric/timestamp comparison operators
    elif operator == 'gt':
        if is_timestamp:
            return (f"{field} > {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"{field} > {param_placeholder}", [value])
        else:
            return (f"{field} > {param_placeholder}", [value])
    
    elif operator == 'lt':
        if is_timestamp:
            return (f"{field} < {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"{field} < {param_placeholder}", [value])
        else:
            return (f"{field} < {param_placeholder}", [value])
    
    elif operator == 'gte':
        if is_timestamp:
            return (f"{field} >= {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"{field} >= {param_placeholder}", [value])
        else:
            return (f"{field} >= {param_placeholder}", [value])
    
    elif operator == 'lte':
        if is_timestamp:
            return (f"{field} <= {param_placeholder}::timestamp", [value])
        elif is_integer:
            return (f"{field} <= {param_placeholder}", [value])
        else:
            return (f"{field} <= {param_placeholder}", [value])
    
    elif operator == 'between':
        # Value should be a list of [min, max]
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError("'between' operator requires a list of exactly 2 values")
        
        if is_timestamp:
            # For timestamps, use < on end date + 1 day to include entire end date
            return (
                f"{field} >= {param_placeholder}::timestamp AND {field} < ({param_placeholder}::timestamp + INTERVAL '1 day')",
                [value[0], value[1]]
            )
        elif is_integer:
            return (
                f"{field} BETWEEN {param_placeholder} AND {param_placeholder}",
                [value[0], value[1]]
            )
        else:
            return (
                f"{field} BETWEEN {param_placeholder} AND {param_placeholder}",
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
    tags=[TAG_SEARCH],
    summary="Simple search with wildcards",
    description=f"See {QUICKSTART_LINK} for details.",
    response_description="Query parameters, count, and array of matching recordss"
    )
@limiter.limit(rate_max)
@track_search_analytics 
async def simple_search(
    request: Request, 
    search_request: SimpleSearchRequest,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format (BASIC tier: JSON only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC)) 
    ):
    f"""
    Execute a simple search with wildcard support.
    All string comparisons are case-insensitive.
    See {QUICKSTART_LINK} for details.
    """

    current_role = current_user["role"]
    user_id = current_user["user_id"]
    billing_cycle = current_user.get("billing_cycle")


    # Validate format access based on user role
    validate_format_access(current_role, format)
    # Validate and enforce limit based on role
    actual_limit = validate_limit_for_role(current_role, search_request.limit, billing_cycle)
    
    # Determine which data field to return based on role
    data_field = get_data_field_for_role(current_role)

    # Build WHERE clause from validated filters
    where_clauses = []
    query_params = []
    
    for filter_item in search_request.filters:
        field = filter_item.field.value
        value = filter_item.value
        
        # Get field data type
        is_string = FieldTypeMap.is_string_field(field)
        
        # Apply flex rules: auto-wrap string fields with wildcards
        if search_request.rules == "flex" and is_string:
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
    where_clause = f" {search_request.logic.value} ".join(where_clauses)

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM vw_bolo_full
                    WHERE {where_clause}
                    LIMIT %s
                """
                # Add limit to params
                query_params.append(actual_limit)
                cur.execute(query, tuple(query_params))
                results = cur.fetchall()
                
        # Extract data and add data_type indicator
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
            
        result_dict = {
            "query": search_request.model_dump(),
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        result_dict["query"]["endpoint"] = "simple"
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_simple_search")
            
    except Exception as e:
        raise Exception(f"Database Error: {str(e)}")

@router.post(
    "/advanced",
    tags=[TAG_SEARCH],
    summary="Advanced search with grouped conditions",
    description=f"See {QUICKSTART_LINK} for details.",
    response_description="Query parameters, count, and array of matching recordss"
)
@limiter.limit(rate_max)
@track_search_analytics
async def advanced_search(
    request: Request, 
    search_request: AdvancedSearchRequest,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format (BASIC tier: JSON only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM)) 
    ):
    f"""
    Execute advanced searches with ehanced operator and grouped condition support.
    All string comparisons are case-insensitive.
    See {QUICKSTART_LINK} for details.
    """
    current_role = current_user["role"]
    user_id = current_user["user_id"] 
    billing_cycle = current_user.get("billing_cycle")


    # Validate format access based on user role
    validate_format_access(current_role, format)
    # Validate and enforce limit based on role
    actual_limit = validate_limit_for_role(current_role, search_request.limit, billing_cycle)
    
    # Determine which data field to return based on role
    data_field = get_data_field_for_role(current_role)
    
    try:
        # Build grouped WHERE clauses from validated request
        group_clauses = []
        query_params = []
        
        for group in search_request.groups:
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
        where_clause = f" {search_request.group_logic.value} ".join(group_clauses)
        
        # Execute search using synchronous psycopg2 (same as simple search)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM vw_bolo_full
                    WHERE {where_clause}
                    LIMIT %s
                """
                # Add limit to params
                query_params.append(actual_limit)
                
                # Execute the query with all parameters
                cur.execute(query, tuple(query_params))
                results = cur.fetchall()
        
        # Extract data and add data_type indicator
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        # Construct response payload
        result_dict = {
            "query": search_request.model_dump(),
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        result_dict["query"]["endpoint"] = "advanced"
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_advanced_search")
    
    except Exception as e:
        logger.error(f"Advanced search error: {str(e)}")
        raise Exception(f"Search error: {str(e)}")


# =============================================================================
# REFERENCE LIST ENDPOINTS
# =============================================================================

@router.get(
    "/list_field_offices",
    tags=[TAG_SEARCH_BY_LIST],
    summary="List of FBI field office locations",
    description="Returns a list of FBI field office locations",
    response_description="List of FBI field office locations"
)
@limiter.limit(rate_max)
@track_search_analytics
async def list_field_offices(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format: json, csv, txt, parquet, or xml (PREMIUM only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """List of FBI field office locations"""
    current_role = current_user["role"]
    user_id = current_user.get("user_id")
    
    validate_format_access(current_role, format)
    
    # Determine limit based on role
    actual_limit = 25 if current_role == UserRole.BASIC else 5000
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT DISTINCT elem AS field_office
                    FROM vw_bolo_full
                    CROSS JOIN LATERAL unnest(field_offices) AS elem
                    WHERE elem IS NOT NULL AND TRIM(elem) <> ''
                    ORDER BY elem
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        # Extract values safely
        field_offices = [row['field_office'] for row in results if row and 'field_office' in row]
        
        # Get role value safely
        role_str = current_role.value if hasattr(current_role, 'value') else str(current_role)
        
        result_dict = {
            "endpoint": "list_field_offices",
            "role": role_str,
            "limit": actual_limit,
            "count": len(field_offices),
            "field_offices": field_offices, 
            "note": "Result set may not reflect all values. Basic subscribers get max 25 records"
        }
        
        request.state.results_count = len(field_offices)
        return format_response(result_dict, format, "bolo_field_offices")
        
    except Exception as e:
        logger.error(f"List field offices error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving field offices: {str(e)}"
        )


@router.get(
    "/list_languages",
    tags=[TAG_SEARCH_BY_LIST],
    summary="List of languages spoken by wanted individuals",
    description="Returns a list of languages spoken by wanted individuals",
    response_description="List of languages spoken by wanted individuals"
)
@limiter.limit(rate_max)
@track_search_analytics
async def list_languages(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format: json, csv, txt, parquet, or xml (PREMIUM only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """Get list of all distinct languages"""
    current_role = current_user["role"]
    user_id = current_user.get("user_id")
    
    validate_format_access(current_role, format)
    
    # Determine limit based on role
    actual_limit = 25 if current_role == UserRole.BASIC else 5000
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT DISTINCT elem AS language
                    FROM vw_bolo_full
                    CROSS JOIN LATERAL unnest(languages) AS elem
                    WHERE elem IS NOT NULL AND TRIM(elem) <> ''
                    ORDER BY elem
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        # Extract values safely
        languages = [row['language'] for row in results if row and 'language' in row and ' ' not in row['language']]
        
        # Get role value safely
        role_str = current_role.value if hasattr(current_role, 'value') else str(current_role)
        
        result_dict = {
            "endpoint": "list_languages",
            "role": role_str,
            "limit": actual_limit,
            "count": len(languages),
            "languages": languages, 
            "note": "Result set may not reflect all values. Basic subscribers get max 25 records"
        }
        
        request.state.results_count = len(languages)
        return format_response(result_dict, format, "bolo_languages")
        
    except Exception as e:
        logger.error(f"List languages error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving languages: {str(e)}"
        )


@router.get(
    "/list_nationality",
    tags=[TAG_SEARCH_BY_LIST],
    summary="List of nationalities of wanted individuals",
    description="Returns a list of nationalities of wanted individuals",
    response_description="List of nationalities of wanted individuals"
)
@limiter.limit(rate_max)
@track_search_analytics
async def list_nationality(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format: json, csv, txt, parquet, or xml (PREMIUM only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """List of nationalities of wanted individuals"""
    current_role = current_user["role"]
    user_id = current_user.get("user_id")
    
    validate_format_access(current_role, format)
    
    # Determine limit based on role
    actual_limit = 25 if current_role == UserRole.BASIC else 5000
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT DISTINCT nationality
                    FROM vw_bolo_full
                    WHERE nationality IS NOT NULL AND TRIM(nationality) <> ''
                    ORDER BY nationality
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        # Extract values safely
        nationality = [row['nationality'] for row in results if row and 'nationality' in row]
        
        # Get role value safely
        role_str = current_role.value if hasattr(current_role, 'value') else str(current_role)
        
        result_dict = {
            "endpoint": "list_nationality",
            "role": role_str,
            "limit": actual_limit,
            "count": len(nationality),
            "list_nationality": nationality, 
            "note": "Result set may not reflect all values. Basic subscribers get max 25 records"
        }
        
        request.state.results_count = len(nationality)
        return format_response(result_dict, format, "bolo_nationality")
        
    except Exception as e:
        logger.error(f"List nationality error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving nationality list: {str(e)}"
        )

@router.get(
    "/list_possible_countries",
    tags=[TAG_SEARCH_BY_LIST],
    summary="List of possible countries associated with wanted individuals and cases",
    description="Returns a list of possible countries associated with wanted individuals and cases",
    response_description="List of possible countries associated with wanted individuals and cases"
)
@limiter.limit(rate_max)
@track_search_analytics
async def list_possible_countries(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format: json, csv, txt, parquet, or xml (PREMIUM only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """List of possible countries associated with wanted individuals and cases"""
    current_role = current_user["role"]
    user_id = current_user.get("user_id")
    
    validate_format_access(current_role, format)
    
    # Determine limit based on role
    actual_limit = 25 if current_role == UserRole.BASIC else 5000
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT DISTINCT elem AS country
                    FROM vw_bolo_full
                    CROSS JOIN LATERAL unnest(possible_countries) AS elem
                    WHERE elem IS NOT NULL AND TRIM(elem) <> ''
                    ORDER BY elem
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        # Extract values safely
        countries = [row['country'] for row in results if row and 'country' in row]
        
        # Get role value safely
        role_str = current_role.value if hasattr(current_role, 'value') else str(current_role)
        
        result_dict = {
            "endpoint": "list_possible_countries",
            "role": role_str,
            "limit": actual_limit,
            "count": len(countries),
            "possible_countries": countries, 
            "note": "Result set may not reflect all values. Basic subscribers get max 25 records"
        }
        
        request.state.results_count = len(countries)
        return format_response(result_dict, format, "bolo_possible_countries")
        
    except Exception as e:
        logger.error(f"List possible countries error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving possible countries: {str(e)}"
        )


@router.get(
    "/list_possible_states",
    tags=[TAG_SEARCH_BY_LIST],
    summary="List of possible USA states associated with wanted individuals and cases",
    description="Returns a list of possible USA states associated with wanted individuals and cases",
    response_description="List of possible USA states associated with wanted individuals and cases"
)
@limiter.limit(rate_max)
@track_search_analytics
async def list_possible_states(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format: json, csv, txt, parquet, or xml (PREMIUM only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
):
    """List of possible USA states associated with wanted individuals and cases"""
    current_role = current_user["role"]
    user_id = current_user.get("user_id")
    
    validate_format_access(current_role, format)
    
    # Determine limit based on role
    actual_limit = 25 if current_role == UserRole.BASIC else 5000
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT DISTINCT elem AS state
                    FROM vw_bolo_full
                    CROSS JOIN LATERAL unnest(possible_states) AS elem
                    WHERE elem IS NOT NULL AND TRIM(elem) <> ''
                    ORDER BY elem
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        # Extract values safely
        states = [row['state'] for row in results if row and 'state' in row]
        
        # Get role value safely
        role_str = current_role.value if hasattr(current_role, 'value') else str(current_role)
        
        result_dict = {
            "endpoint": "list_possible_states",
            "role": role_str,
            "limit": actual_limit,
            "count": len(states),
            "possible_states": states, 
            "note": "Result set may not reflect all values. Basic subscribers get max 25 records"
        }
        
        request.state.results_count = len(states)
        return format_response(result_dict, format, "bolo_possible_states")
        
    except Exception as e:
        logger.error(f"List possible states error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving possible states: {str(e)}"
        )
        
@router.get(
    "/list_race",
    tags=[TAG_SEARCH_BY_LIST],
    summary="List of races of origin associated with wanted individuals and cases",
    description="Returns list of races of origin associated with wanted individuals and cases",
    response_description="List of races of origin associated with wanted individuals and cases"
    )
@limiter.limit(rate_max)
@track_search_analytics
async def list_race(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format: json, csv, txt, parquet, or xml (PREMIUM only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.BASIC))
    ):
    """List of races of origin associated with wanted individuals and cases"""
    current_role = current_user["role"]
    user_id = current_user.get("user_id")
    
    validate_format_access(current_role, format)
    
    # Determine limit based on role
    actual_limit = 25 if current_role == UserRole.BASIC else 5000
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = """
                    SELECT DISTINCT race
                    FROM vw_bolo_full
                    WHERE race IS NOT NULL AND TRIM(race) <> ''
                    ORDER BY race
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        # Extract values safely
        races = [row['race'] for row in results if row and 'race' in row]
        
        # Get role value safely
        role_str = current_role.value if hasattr(current_role, 'value') else str(current_role)
        
        result_dict = {
            "endpoint": "list_race",
            "role": role_str,
            "limit": actual_limit,
            "count": len(races),
            "races": races, 
            "note": "Result set may not reflect all values. Basic subscribers get max 25 records"
        }
        
        request.state.results_count = len(races)
        return format_response(result_dict, format, "bolo_races")
        
    except Exception as e:
        logger.error(f"List races error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving list of subject races: {str(e)}"
        )


# =============================================================================
# CLASSIFICATION-BASED SEARCH ENDPOINTS
# =============================================================================

@router.get(
    "/category_top_ten",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="FBI ten most wanted fugitives",
    description="Returns records of a given class",
    response_description="FBI ten most wanted fugitives"
    )
@limiter.limit(rate_max)
@track_search_analytics
async def get_top_ten(
    request: Request,
    format: ResponseFormatBasic = Query(default=ResponseFormatBasic.JSON, description="Response format (BASIC tier: JSON only)"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Get FBI ten most wanted fugitives"""
    current_role = current_user["role"]
    user_id = current_user["user_id"]
    
    validate_format_access(current_role, format)
    
    actual_limit = 10
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('topten')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_top_ten",
                "classification": "topten"
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_top_ten")
    
    except Exception as e:
        logger.error(f"Top Ten search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_top_reward",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Wanted individuals and cases with high-dollar rewards >= USD$1 Million",
    description="Returns records of a given class",
    response_description="Wanted individuals and cases with high-dollar rewards >= USD$1 Million"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_top_reward(
    request: Request,
    limit: int = Query(default=25, ge=1, le=5000, description="Maximum results to return"),
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Wanted individuals and cases with high-dollar rewards >= USD$1 Million"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('top_reward')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_top_reward",
                "classification": "top_reward",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_top_reward")
    
    except Exception as e:
        logger.error(f"Top Reward search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_additional",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Additional violent individuals and cases",
    description="Returns records of a given class",
    response_description="Additional violent individuals and cases"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_additional_info(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Additional violent individuals and cases"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('additional')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_additional",
                "classification": "additional",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_additional_info")
    
    except Exception as e:
        logger.error(f"Additional Info search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_crimes_against_children",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to crimes against children",
    description="Returns records of a given class",
    response_description="Individuals and cases related to crimes against children"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_crimes_against_children(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to crimes against children"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('cac')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_crimes_against_children",
                "classification": "cac",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_crimes_against_children")
    
    except Exception as e:
        logger.error(f"Crimes Against Children search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_criminal_enterprise_investigations",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to criminal enterprise investigations",
    description="Returns records of a given class",
    response_description="Individuals and cases related to criminal enterprise investigations"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_criminal_enterprise_investigations(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to criminal enterprise investigations"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('cei')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_criminal_enterprise_investigations",
                "classification": "cei",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_criminal_enterprise_investigations")
    
    except Exception as e:
        logger.error(f"Criminal Enterprise Investigations search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_counterintelligence",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to counterintelligence",
    description="Returns records of a given class",
    response_description="Individuals and cases related to counterintelligences"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_counterintelligence(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to counterintelligence"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('counterintelligence')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_counterintelligence",
                "classification": "counterintelligence",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_counterintelligence")
    
    except Exception as e:
        logger.error(f"Counterintelligence search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_cyber_crimes",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to cyber crimes",
    description="Returns records of a given class",
    response_description="Individuals and cases related to cyber crimes"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_cyber_crimes(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to cyber crimes"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('cyber')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_cyber_crimes",
                "classification": "cyber",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_cyber_crimes")
    
    except Exception as e:
        logger.error(f"Cyber Crimes search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_domestic_terrorism",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to domestic terrorism",
    description="Returns records of a given class",
    response_description="Individuals and cases related to domestic terrorism"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_domestic_terrorism(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to domestic terrorism"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('dt')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_domestic_terrorism",
                "classification": "dt",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_domestic_terrorism")
    
    except Exception as e:
        logger.error(f"Domestic Terrorism search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_endangered_child_alert_program",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to the Endangered Child Alert Program (ECAP)",
    description="Returns records of a given class",
    response_description="Individuals and cases related to the Endangered Child Alert Program (ECAP)"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_endangered_child_alert_program(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to the Endangered Child Alert Program (ECAP)"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('ecap')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_endangered_child_alert_program",
                "classification": "ecap",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_ecap")
    
    except Exception as e:
        logger.error(f"ECAP search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_human_trafficking",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to human trafficking",
    description="Returns records of a given class",
    response_description="Individuals and cases related to human trafficking"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_human_trafficking(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to human trafficking"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('human-trafficking')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_human_trafficking",
                "classification": "human-trafficking",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_human_trafficking")
    
    except Exception as e:
        logger.error(f"Human Trafficking search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_kidnap_missing",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to kidnappings and missing persons",
    description="Returns records of a given class",
    response_description="Individuals and cases related to kidnappings and missing persons"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_kidnap_missing(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to kidnappings and missing persons"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('kidnap')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_kidnap_missing",
                "classification": "kidnap",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_kidnap_missing")
    
    except Exception as e:
        logger.error(f"Kidnap/Missing search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_known_bank_robbers",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to known bank robbers",
    description="Returns records of a given class",
    response_description="Individuals and cases related to known bank robbers"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_known_bank_robbers(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to known bank robbers"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('known-bank-robbers')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_known_bank_robbers",
                "classification": "known-bank-robbers",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_known_bank_robbers")
    
    except Exception as e:
        logger.error(f"Known Bank Robbers search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_law_enforcement_assistance",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to law enforcement assistance",
    description="Returns records of a given class",
    response_description="Individuals and cases related to law enforcement assistance"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_law_enforcement_assistance(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to law enforcement assistance"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('law-enforcement-assistance')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_law_enforcement_assistance",
                "classification": "law-enforcement-assistance",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_law_enforcement_assistance")
    
    except Exception as e:
        logger.error(f"Law Enforcement Assistance search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_murders",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to murder",
    description="Returns records of a given class",
    response_description="Individuals and cases related to murder"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_murders(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to murder"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('murders')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_murders",
                "classification": "murders",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_murders")
    
    except Exception as e:
        logger.error(f"Murders search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_kidnap_parental",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to parental kidnappings",
    description="Returns records of a given class",
    response_description="Individuals and cases related to parental kidnappings"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_kidnap_parental(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to parental kidnappings"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('parental-kidnappings')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_kidnap_parental",
                "classification": "parental-kidnappings",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_kidnap_parental")
    
    except Exception as e:
        logger.error(f"Parental Kidnappings search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_seeking_info",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases for whom additional information is sought",
    description="Returns records of a given class",
    response_description="Individuals and cases for whom additional information is sought"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_seeking_info(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases for whom additional information is sought"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('seeking-info')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_seeking_info",
                "classification": "seeking-info",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_seeking_info")
    
    except Exception as e:
        logger.error(f"Seeking Info search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_terror_info",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to terrorism for whom additional information is sought",
    description="Returns records of a given class",
    response_description="Individuals and cases related to terrorism for whom additional information is sought"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_terror_info(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to terrorism for whom additional information is sought"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('terrorinfo')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_terror_info",
                "classification": "terrorinfo",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_terror_info")
    
    except Exception as e:
        logger.error(f"Terror Info search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_violent_criminal_apprehension_program",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to the Violent Criminal Apprehension Program (ViCAP)",
    description="Returns records of a given class",
    response_description="Individuals and cases related to the Violent Criminal Apprehension Program (ViCAP)"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_violent_criminal_apprehension_program(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to the Violent Criminal Apprehension Program (ViCAP)"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('vicap')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_violent_criminal_apprehension_program",
                "classification": "vicap",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_vicap")
    
    except Exception as e:
        logger.error(f"ViCAP search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_wanted_terrorists",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to wanted terrorists",
    description="Returns records of a given class",
    response_description="Individuals and cases related to wanted terrorists"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_wanted_terrorists(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to wanted terrorists"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('wanted_terrorists')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_wanted_terrorists",
                "classification": "wanted_terrorists",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_wanted_terrorists")
    
    except Exception as e:
        logger.error(f"Wanted Terrorists search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )


@router.get(
    "/category_white_collar_crimes",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to white-collar crimes",
    description="Returns records of a given class",
    response_description="Individuals and cases related to white-collar crimes"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_white_collar_crimes(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to white-collar crimes"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('wcc')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_white_collar_crimes",
                "classification": "wcc",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_white_collar_crimes")
    
    except Exception as e:
        logger.error(f"White Collar Crimes search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )

@router.get(
    "/category_case_of_the_week",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases identified by the FBI as Case of the Week",
    description="Returns records of a given class",
    response_description="Individuals and cases identified by the FBI as Case of the Week"
)
@limiter.limit(rate_max)
@track_search_analytics
async def get_case_of_the_week(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases identified by the FBI as Case of the Week"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('case_of_the_week')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_case_of_the_week",
                "classification": "case_of_the_week",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_white_collar_crimes")
    
    except Exception as e:
        logger.error(f"Case of the Week search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )
    

@router.get(
    "/category_native_american",
    tags=[TAG_SEARCH_BY_CATEGORY],
    summary="Individuals and cases related to Native Americans",
    description="Returns records of a given class",
    response_description="Individuals and cases related to Native Americans"
)
@limiter.limit(rate_max)
@track_search_analytics 
async def get_native_american(
    request: Request,
    format: ResponseFormatPremium = Query(default=ResponseFormatPremium.JSON, description="Response format: json, csv, txt, parquet, or xml"),
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """Individuals and cases related to Native Americans"""
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This endpoint is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    validate_format_access(current_role, format)
    actual_limit = validate_limit_for_role(current_role, 5000, billing_cycle)
    data_field = get_data_field_for_role(current_role)
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                query = f"""
                    SELECT {data_field}
                    FROM ftn_bolo_group('native_american')
                    LIMIT %s
                """
                cur.execute(query, (actual_limit,))
                results = cur.fetchall()
        
        items = []
        data_type = "clean" if data_field == "full_data_clean" else "raw"
        
        for row in results:
            item_data = row[data_field]
            items.append({
                "data_type": data_type,
                "data": item_data
            })
        
        result_dict = {
            "query": {
                "endpoint": "category_native_american",
                "classification": "native_american",
                "limit": actual_limit
            },
            "role": current_role.value,
            "resultcount": len(items),
            "items": items
        }
        request.state.results_count = len(items)  # Store for analytics
        return format_response(result_dict, format, "bolo_native_american")
    
    except Exception as e:
        logger.error(f"Native American search error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search error: {str(e)}"
        )

@router.get(
    "/",
    tags=[TAG_SEARCH],
    summary="API Information",
    description="Get information about this API and available endpoints"
)
async def root(current_user: dict = Depends(require_jwt_role(UserRole.ADMIN))):
    """Return API information and usage guide - accessible to all roles"""
    return {
        "name": "Advanced Search API",
        "version": "1.0.0",
        "endpoints": {
            "/simple": "Simple wildcard-based search (BASIC role or higher)",
            "/advanced": "Advanced search with grouped conditions (PREMIUM role or higher)"
        },
        "classification_endpoints": {
            "description": "FBI wanted persons by classification category",
            "access_note": "category_top_ten available to PREMIUM (any billing cycle); all others require PREMIUM annual subscription only",
            "endpoints": {
                "/category_top_ten": "FBI Ten Most Wanted Fugitives (PREMIUM any billing)",
                "/category_top_reward": "High reward cases $1M+ (PREMIUM annual subscription only)",
                "/category_additional": "Additional Information (PREMIUM annual subscription only)",
                "/category_crimes_against_children": "Crimes Against Children (PREMIUM annual subscription only)",
                "/category_criminal_enterprise_investigations": "Criminal Enterprise Investigations (PREMIUM annual subscription only)",
                "/category_counterintelligence": "Counterintelligence (PREMIUM annual subscription only)",
                "/category_cyber_crimes": "Cyber Crimes (PREMIUM annual subscription only)",
                "/category_domestic_terrorism": "Domestic Terrorism (PREMIUM annual subscription only)",
                "/category_endangered_child_alert_program": "ECAP - Endangered Child Alert Program (PREMIUM annual subscription only)",
                "/category_human_trafficking": "Human Trafficking (PREMIUM annual subscription only)",
                "/category_kidnap_missing": "Kidnappings and Missing Persons (PREMIUM annual subscription only)",
                "/category_known_bank_robbers": "Known Bank Robbers (PREMIUM annual subscription only)",
                "/category_law_enforcement_assistance": "Law Enforcement Assistance (PREMIUM annual subscription only)",
                "/category_murders": "Murders (PREMIUM annual subscription only)",
                "/category_kidnap_parental": "Parental Kidnappings (PREMIUM annual subscription only)",
                "/category_seeking_info": "Seeking Information (PREMIUM annual subscription only)",
                "/category_terror_info": "Terrorism Information (PREMIUM annual subscription only)",
                "/category_violent_criminal_apprehension_program": "ViCAP - Violent Criminal Apprehension Program (PREMIUM annual subscription only)",
                "/category_wanted_terrorists": "Wanted Terrorists (PREMIUM annual subscription only)",
                "/category_white_collar_crimes": "White Collar Crimes (PREMIUM annual subscription only)",
                "/category_native_american": "Native American Cases (PREMIUM annual subscription only)"
            }
        },
        "access_levels": {
            "PUBLIC": "Root endpoints only",
            "BASIC": "Simple search, max 25 results, raw data, JSON format only",
            "PREMIUM (monthly)": "Simple + Advanced search, max 25 results, clean data, all formats (JSON/CSV/TXT/XML)",
            "PREMIUM (annual)": "Simple + Advanced search + Category endpoints, max 5000 results, clean data, all formats (JSON/CSV/TXT/XML)"
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
        "response_formats": {
            "description": "Search endpoints support multiple response formats via the 'format' query parameter",
            "access_by_role": {
                "BASIC": ["json"],
                "PREMIUM": ["json", "csv", "txt", "xml"]
            },
            "formats": {
                "json": "Default JSON format with full metadata (all roles)",
                "csv": "Comma-separated values for spreadsheet import (PREMIUM/ADMIN only)",
                "txt": "Human-readable plain text BOLO format (PREMIUM/ADMIN only)",
                "xml": "Structured XML for RMS/CAD system integration (PREMIUM/ADMIN only)"
            },
            "example": "/v1/search/simple?format=csv",
            "note": "BASIC users attempting to use csv, txt, or xml formats will receive a 403 Forbidden error"
        },
        "result_limits": [25, 50, 100, 250, 500, 5000],
        "default_limit": 25
    }

# =============================================================================
# PREMIUM ANNUAL SUBSCRIBER ENDPOINTS - DOCUMENTS ARCHIVE
# =============================================================================

@router.get(
    "/documents_info",
    tags=[TAG_SEARCH],
    summary="Documents Archive Information",
    description="""
    Get information about the available BOLO documents archive.
    
    **Access:** PREMIUM subscription with annual billing cycle
    
    Returns archive availability, file size, and generation timestamp.
    """
    )
@limiter.limit(rate_max)
async def get_documents_info(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """
    Get information about the current documents archive.
    
    **Access:** PREMIUM subscription with annual billing cycle
    
    Returns:
    - Archive availability
    - File size
    - Generation timestamp
    """
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    
    # Check access: ADMIN always allowed, PREMIUM must have annual billing
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Documents archive is only available to annual subscribers. "
                       "Upgrade to an annual plan to access this feature."
            )
    
    try:
        info = get_archive_info()
        
        if not info:
            return {
                "available": False,
                "message": "Documents archive is not currently available. "
                           "Please check back later."
            }
        
        return {
            "available": True,
            "size_mb": info.get("size_mb"),
            "size_bytes": info.get("size_bytes"),
            "generated_at": info.get("modified_at"),
            "download_endpoint": "/v1/search/documents_download"
        }
        
    except Exception as e:
        logger.error(f"Error getting archive info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving archive information: {str(e)}"
        )


@router.get(
    "/documents_download",
    tags=[TAG_SEARCH],
    summary="Download Documents Archive",
    description="""
    Download the complete BOLO documents archive (ZIP file).
    
    **Access:** PREMIUM subscription with annual billing cycle
    
    The archive contains:
    - Per-person folders with meaningful names
    - info.txt summary for each person
    - All available documents and images
    - Root manifest.txt with complete statistics
    
    **Note:** This is a large file (typically 100-500 MB). Download may take several minutes.
    """,
    response_class=FileResponse,
    responses={
        200: {
            "description": "ZIP file download",
            "content": {"application/zip": {}}
        },
        403: {
            "description": "Access denied - annual subscription required"
        },
        404: {
            "description": "Archive not available"
        }
    }
    )
@limiter.limit("3/hour")  # More restrictive limit for large file downloads
async def download_documents_archive(
    request: Request,
    current_user: dict = Depends(require_jwt_role(UserRole.PREMIUM))
    ):
    """
    Download the complete BOLO documents archive.
    
    **Access:** PREMIUM subscription with annual billing cycle
    
    Returns the bolodoc_files.zip archive containing all BOLO documents
    organized by person with info.txt summaries and a root manifest.
    
    This is a large file download. Rate limited to 3 downloads per hour.
    """
    current_role = current_user["role"]
    billing_cycle = current_user.get("billing_cycle")
    user_id = current_user.get("user_id")
    
    # Check access: ADMIN always allowed, PREMIUM must have annual billing
    if current_role != UserRole.ADMIN:
        if billing_cycle != "annual":
            logger.warning(f"User {user_id} attempted archive download without annual subscription")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Documents archive download is only available to annual subscribers. "
                       "Your current billing cycle is: " + (billing_cycle or "none") + ". "
                       "Upgrade to an annual plan to access this feature."
            )
    
    try:
        archive_path = get_archive_file_path()
        
        if not archive_path:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Documents archive is not currently available. "
                       "Please check back later or contact support."
            )
        
        logger.info(f"User {user_id} downloading documents archive")
        
        return FileResponse(
            path=str(archive_path),
            media_type="application/zip",
            filename="bolodoc_files.zip",
            headers={
                "Content-Disposition": "attachment; filename=bolodoc_files.zip"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving archive download: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error downloading archive: {str(e)}"
        )