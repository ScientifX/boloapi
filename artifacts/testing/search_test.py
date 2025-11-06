#!/usr/bin/env python3
"""
Random Search Endpoint Tester
Tests /simple and /advanced search endpoints with random but valid/invalid payloads

Set test_type to "valid" or "invalid" to control behavior:
- "valid": Generate valid payloads (original behavior)
- "invalid": Generate invalid payloads to test validation error handling
"""

import json
import random
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import sys
import csv

# ============================================================================
# CONFIGURATION
# ============================================================================
test_type = "valid"  # Change to "invalid" to test error handling
csv_mode = "overwrite"  # "overwrite" or "append"
count_from = 1000
count_to = 1000

BASE_URL = "http://127.0.0.1:8000/api/search"
SIMPLE_ENDPOINT = f"{BASE_URL}/simple"
ADVANCED_ENDPOINT = f"{BASE_URL}/advanced"

# Test values from test_values.txt
TEST_VALUES = {
    "possible_states": [
        "albany", "albuquerque", "anchorage", "atlanta", "baltimore", "birmingham",
        "boston", "buffalo", "charlotte", "chicago", "cincinnati", "cleveland",
        "columbia", "dallas", "denver", "detroit", "elpaso", "honolulu", "houston",
        "indianapolis", "jackson", "kansascity", "lasvegas", "littlerock", "losangeles",
        "louisville", "miami", "milwaukee", "minneapolis", "mobile", "nashville",
        "newark", "newhaven", "neworleans", "newyork", "norfolk", "oklahomacity",
        "omaha", "philadelphia", "phoenix", "pittsburgh", "portland", "richmond",
        "sacramento", "saltlakecity", "sanantonio", "sandiego", "sanfrancisco",
        "sanjuan", "seattle", "springfield", "stlouis", "tampa", "washingtondc",
        # Also include normalized codes
        "US-AL", "US-AR", "US-AZ", "US-CA", "US-CO", "US-CT", "US-DC", "US-FL",
        "US-GA", "US-HI", "US-IL", "US-IN", "US-KY", "US-LA", "US-MA", "US-MD",
        "US-ME", "US-MI", "US-MN", "US-MS", "US-NC", "US-NE", "US-NJ", "US-NV",
        "US-NY", "US-OH", "US-OK", "US-OR", "US-PA", "US-PR", "US-RI", "US-SC",
        "US-SD", "US-TN", "US-TX", "US-UM", "US-UT", "US-VA", "US-VT", "US-WA",
        "US-WI", "US-WV", "US-WY"
    ],
    "languages": [
        "Arabic", "Azeri", "Bulgarian", "Cantonese", "Chinese", "English", "Farsi",
        "French", "Fulani", "German", "Hindi", "Italian", "Japanese", "Korean",
        "Kurdish", "Mandarin", "Navajo", "Pashto", "Portuguese", "Russian", "Somali",
        "Spanish", "Swedish", "Tausug", "Turkish", "Unknown", "Urdu", "Vietnamese"
    ],
    "eyes": ["black", "blue", "brown", "dark", "green", "hazel"],
    "age_max": list(range(4, 76)),
    "age_min": list(range(2, 76)),
    "subjects": [
        "Additional Violent Crimes", "Capitol", "Case of the Week", "China Threat",
        "Counterintelligence", "Crimes Against Children", "Criminal Enterprise Investigations",
        "Cyber's Most Wanted", "Domestic Terrorism", "ECAP", "Endangered Child Alert Program",
        "Human Trafficking", "Indian Country", "Iran", "John Doe", "Kidnappings/Missing Persons",
        "Law Enforcement Assistance", "Most Wanted Terrorists", "Navajo", "Operation Legend",
        "Parental Kidnapping", "Seeking Information", "Seeking Information - Terrorism",
        "Ten Most Wanted Fugitives", "Transnational Repression",
        "ViCAP Homicides and Sexual Assaults", "ViCAP Missing Persons",
        "ViCAP Unidentified Persons", "Violent Crime - Murders", "White Collar Crimes"
    ]
}

# Field metadata
STRING_FIELDS = [
    "build", "caution", "complexion", "description", "details", "eyes", "eyes_raw",
    "hair", "hair_raw", "nationality", "ncic", "path", "pathid", "person_classification",
    "place_of_birth", "poster_classification", "poster_url", "race", "race_raw",
    "remarks", "reward_text", "scars_and_marks", "sex", "status", "title", "url",
    "warning_message", "weight"
]

INTEGER_FIELDS = [
    "age_max", "age_min", "height_max", "height_min", "reward_max", "reward_min",
    "weight_max", "weight_min"
]

TIMESTAMP_FIELDS = ["modified", "publication"]

TEXT_ARRAY_FIELDS = [
    "aliases", "dates_of_birth_used", "field_offices", "languages", "legat_names",
    "locations", "occupations", "possible_countries", "possible_states", "subjects",
    "suspects"
]

ALL_SEARCHABLE_FIELDS = STRING_FIELDS + INTEGER_FIELDS + TIMESTAMP_FIELDS + TEXT_ARRAY_FIELDS

# Operators by field type
STRING_OPERATORS = ["equals", "contains", "starts_with", "ends_with"]
NUMERIC_OPERATORS = ["equals", "gt", "lt", "gte", "lte", "between"]
ARRAY_OPERATORS = ["equals", "contains", "starts_with", "ends_with"]

SAMPLE_VALUES = {
    "title": ["Murder", "Kidnapping", "Robbery", "Assault", "Theft", "Fraud", "Burglary"],
    "sex": ["Male", "Female"],
    "race": ["White", "Black", "Asian", "Hispanic", "Native American", "Other"],
    "hair": ["Black", "Brown", "Blonde", "Red", "Gray", "Bald"],
    "hair_raw": ["Black", "Brown", "Blonde", "Red", "Gray", "White", "Bald"],
    "eyes_raw": ["Black", "Blue", "Brown", "Green", "Hazel", "Gray"],
    "build": ["Slender", "Medium", "Heavy", "Muscular", "Athletic"],
    "complexion": ["Light", "Medium", "Dark", "Fair", "Olive"],
    "status": ["Active", "Inactive", "Captured", "Deceased"],
    "caution": ["Armed and Dangerous", "Dangerous", "May be Armed", "Approach with Caution"],
    "nationality": ["American", "Mexican", "Canadian", "Chinese", "Russian", "British"],
    "person_classification": ["Fugitive", "Missing", "Wanted", "Suspect"],
    "poster_classification": ["wanted", "missing", "kidnap", "suspect"],
    "field_offices": ["newyork", "losangeles", "chicago", "miami", "dallas", "boston"],
    "ncic": ["W123456789", "M987654321", "F456789123"],
    "place_of_birth": ["New York", "Los Angeles", "Chicago", "Houston", "Phoenix"],
    "reward_text": ["Up to $100,000", "Up to $50,000", "Up to $25,000", "Reward Offered"],
    "description": ["armed robbery", "murder suspect", "kidnapping", "fraud", "assault"],
    "details": ["suspect fled the scene", "last seen in", "wanted for", "armed and dangerous"],
    "remarks": ["may have changed appearance", "known to frequent", "has ties to"],
    "scars_and_marks": ["scar on left arm", "tattoo on right shoulder", "birthmark on face"],
    "warning_message": ["Armed and Dangerous", "Do Not Approach", "Contact FBI"],
    "locations": ["California", "Texas", "New York", "Florida", "Illinois"],
    "occupations": ["Construction", "Mechanic", "Sales", "Driver", "Teacher"],
    "suspects": ["John Doe", "Jane Smith", "Unknown Male", "Unknown Female"],
    "dates_of_birth_used": ["1980", "1975", "1990", "1985"],
    "legat_names": ["London", "Paris", "Mexico City", "Tokyo"],
    "possible_countries": ["USA", "Mexico", "Canada", "Colombia", "Russia"],
}

# ============================================================================
# INVALID DATA GENERATORS
# ============================================================================

# Invalid field names (typos, non-existent fields)
INVALID_FIELD_NAMES = [
    "titlex", "group_logicx", "filterz", "rulez", "age_maximum", "reward_amount",
    "first_name", "last_name", "date_of_birth", "heightx", "weightx", "eyecolor",
    "haircolor", "languagez", "subjectz", "locationz", "reward_maxx"
]

# Invalid operators
INVALID_OPERATORS = [
    "like", "not_equals", "greater", "less", "in", "not_in", "matches", "regex"
]

# Invalid logic operators
INVALID_LOGIC = ["XOR", "NOT", "NAND", "NOR", "and", "or", "&&", "||"]

# Invalid date formats
INVALID_DATES = [
    "2024-13-01",  # Invalid month
    "2024-02-30",  # Invalid day
    "24-01-15",    # Wrong format
    "2024/01/15",  # Wrong separator
    "01-15-2024",  # Wrong order
    "2024-1-5",    # Missing leading zeros
    "not-a-date",  # Garbage
    "2024-00-01",  # Zero month
    "2024-01-00",  # Zero day
]

# Invalid enum values
INVALID_RULE_MODES = ["loose", "normal", "tight", "strict_mode", "flexible"]
INVALID_LIMITS = [0, 25, 75, 150, 1000, -1, "fifty"]


class SearchTester:
    def __init__(self):
        self.results = {
            "total_tests": 0,
            "successes": 0,
            "failures": 0,
            "tests": []
            }
        self.log_filename = "search_test_log.csv"
        self.test_type = test_type
        self.csv_mode = csv_mode  # Store for reference
    
    def generate_random_date(self) -> str:
        """Generate a random date between 2000-2025"""
        start_date = datetime(2000, 1, 1)
        end_date = datetime(2025, 12, 31)
        time_delta = end_date - start_date
        random_days = random.randint(0, time_delta.days)
        random_date = start_date + timedelta(days=random_days)
        return random_date.strftime('%Y-%m-%d')
    
    def get_field_value(self, field: str, field_type: str) -> Any:
        """Generate appropriate value for a field"""
        # Check if field has test values
        if field in TEST_VALUES:
            return random.choice(TEST_VALUES[field])
        
        # Check if field has sample values
        if field in SAMPLE_VALUES:
            return random.choice(SAMPLE_VALUES[field])
        
        # Generate based on field type
        if field_type == "integer":
            if "age" in field:
                return random.randint(18, 75)
            elif "height" in field:
                return random.randint(48, 84)  # inches
            elif "weight" in field:
                return random.randint(100, 300)  # pounds
            elif "reward" in field:
                return random.choice([5000, 10000, 25000, 50000, 100000, 250000, 500000])
            else:
                return random.randint(1, 100)
        
        elif field_type == "timestamp":
            return self.generate_random_date()
        
        elif field_type == "text_array":
            # Return a single value for array search
            return f"test_{field}_{random.randint(1, 100)}"
        
        else:  # string
            return f"test_{field}_{random.randint(1, 100)}"
    
    def get_invalid_value(self, field: str, field_type: str) -> Any:
        """Generate INVALID value for a field to trigger validation errors"""
        error_type = random.choice([
            "wrong_type",
            "bad_format", 
            "empty",
            "null",
            "out_of_range"
        ])
        
        if error_type == "wrong_type":
            if field_type == "integer":
                # Return string, boolean, or float for integer field
                return random.choice([
                    "not_a_number",
                    True,
                    False,
                    3.14159,
                    "123.45"
                ])
            elif field_type == "timestamp":
                # Return invalid date formats
                return random.choice(INVALID_DATES)
            else:  # string or text_array
                # Return number or boolean for string field
                return random.choice([
                    12345,
                    True,
                    False,
                    None,
                    ["array", "not", "string"]
                ])
        
        elif error_type == "bad_format":
            if field_type == "timestamp":
                return random.choice(INVALID_DATES)
            elif field_type == "integer":
                return "12.34.56"  # Invalid number format
            else:
                # Return string with control characters that WILL be rejected
                return f"test\x00data"  # Null byte - violates your middleware validation
        
        elif error_type == "empty":
            return ""
        
        elif error_type == "null":
            return None
        
        elif error_type == "out_of_range":
            if field_type == "integer":
                # Return value out of bounds of an int4 for age/height fields
                return 2147483648 
            else:
                return "x" * 150  # Exceeds 100 char limit in validate_string()

        return "invalid"
    
    def add_wildcards(self, value: str) -> str:
        """Randomly add wildcards to a string value"""
        if not isinstance(value, str):
            return value
        
        wildcard_choice = random.choice([
            "none",      # 25% no wildcards
            "both",      # 25% *value*
            "start",     # 25% *value
            "end"        # 25% value*
            ])
        
        if wildcard_choice == "both":
            return f"*{value}*"
        elif wildcard_choice == "start":
            return f"*{value}"
        elif wildcard_choice == "end":
            return f"{value}*"
        else:
            return value
    
    def get_field_type(self, field: str) -> str:
        """Determine field type"""
        if field in INTEGER_FIELDS:
            return "integer"
        elif field in TIMESTAMP_FIELDS:
            return "timestamp"
        elif field in TEXT_ARRAY_FIELDS:
            return "text_array"
        else:
            return "string"
    
    def generate_simple_search(self) -> Dict[str, Any]:
        """Generate a random simple search payload"""
        if self.test_type == "invalid":
            return self.generate_invalid_simple_search()
        
        num_filters = random.randint(1, 7)
        fields = random.sample(ALL_SEARCHABLE_FIELDS, num_filters)
        
        filters = []
        for field in fields:
            field_type = self.get_field_type(field)
            value = self.get_field_value(field, field_type)
            
            # Convert to string and add wildcards for string fields
            if field_type in ["string", "text_array"]:
                value = str(value)
                value = self.add_wildcards(value)
            else:
                value = str(value)
            
            filters.append({
                "field": field,
                "value": value
            })
        
        return {
            "filters": filters,
            "logic": random.choice(["AND", "OR"]),
            "limit": random.choice([50, 100, 250, 500]),
            "rules": random.choice(["strict", "flex"])
        }
    
    def generate_invalid_simple_search(self) -> Dict[str, Any]:
        """Generate an INVALID simple search payload to test error handling"""
        error_category = random.choice([
            "invalid_field_name",
            "invalid_property_name",
            "wrong_value_type",
            "invalid_logic",
            "invalid_limit",
            "invalid_rules",
            "missing_required",
            "empty_filters"
        ])
        
        if error_category == "invalid_field_name":
            # Use invalid field name in filter
            return {
                "filters": [
                    {
                        "field": random.choice(INVALID_FIELD_NAMES),
                        "value": "test"
                    }
                ],
                "logic": "AND",
                "limit": 50,
                "rules": "strict"
            }
        
        elif error_category == "invalid_property_name":
            # Typo in top-level property
            payload = {
                "filters": [{"field": "title", "value": "test"}],
                "logic": "AND",
                "limit": 50,
                "rules": "strict"
            }
            # Add typo
            typo_key = random.choice(["filterz", "logicx", "limitx", "rulez"])
            payload[typo_key] = payload.pop(random.choice(["filters", "logic", "limit", "rules"]))
            return payload
        
        elif error_category == "wrong_value_type":
            # Submit wrong type for a field
            field = random.choice(ALL_SEARCHABLE_FIELDS)
            field_type = self.get_field_type(field)
            return {
                "filters": [
                    {
                        "field": field,
                        "value": self.get_invalid_value(field, field_type)
                    }
                ],
                "logic": "AND",
                "limit": 50,
                "rules": "strict"
            }
        
        elif error_category == "invalid_logic":
            return {
                "filters": [{"field": "title", "value": "test"}],
                "logic": random.choice(INVALID_LOGIC),
                "limit": 50,
                "rules": "strict"
            }
        
        elif error_category == "invalid_limit":
            return {
                "filters": [{"field": "title", "value": "test"}],
                "logic": "AND",
                "limit": random.choice(INVALID_LIMITS),
                "rules": "strict"
            }
        
        elif error_category == "invalid_rules":
            return {
                "filters": [{"field": "title", "value": "test"}],
                "logic": "AND",
                "limit": 50,
                "rules": random.choice(INVALID_RULE_MODES)
            }
        
        elif error_category == "missing_required":
            # Only "filters" is actually required (others have defaults)
            return {
                "logic": "AND",
                "limit": 50,
                "rules": "strict"
                # Missing "filters" - this WILL cause an error
            }
                
        elif error_category == "empty_filters":
            return {
                "filters": [],
                "logic": "AND",
                "limit": 50,
                "rules": "strict"
            }
        
        return {}
    
    def generate_advanced_search(self) -> Dict[str, Any]:
        """Generate a random advanced search payload"""
        if self.test_type == "invalid":
            return self.generate_invalid_advanced_search()
        
        num_groups = random.randint(1, 3)
        groups = []
        
        for _ in range(num_groups):
            num_rules = random.randint(1, 7)
            fields = random.sample(ALL_SEARCHABLE_FIELDS, num_rules)
            
            rules = []
            for field in fields:
                field_type = self.get_field_type(field)
                
                # Select appropriate operator for field type
                if field_type == "integer":
                    # Weight operators: more equals/gte/lte, fewer between
                    operator = random.choices(
                        NUMERIC_OPERATORS,
                        weights=[20, 15, 15, 20, 20, 10],  # between gets lower weight
                        k=1
                    )[0]
                elif field_type == "timestamp":
                    operator = random.choices(
                        NUMERIC_OPERATORS,
                        weights=[20, 15, 15, 20, 20, 10],
                        k=1
                    )[0]
                elif field_type == "text_array":
                    operator = random.choice(ARRAY_OPERATORS)
                else:  # string
                    operator = random.choice(STRING_OPERATORS)
                
                # Generate value(s) based on operator
                if operator == "between":
                    # Generate two values ensuring min < max
                    val1 = self.get_field_value(field, field_type)
                    val2 = self.get_field_value(field, field_type)
                    
                    if field_type == "integer":
                        min_val = min(int(val1), int(val2))
                        max_val = max(int(val1), int(val2))
                        # Ensure they're different
                        if min_val == max_val:
                            max_val += 10
                        value = [min_val, max_val]
                    elif field_type == "timestamp":
                        date1 = datetime.strptime(val1, '%Y-%m-%d')
                        date2 = datetime.strptime(val2, '%Y-%m-%d')
                        min_date = min(date1, date2)
                        max_date = max(date1, date2)
                        # Ensure they're different
                        if min_date == max_date:
                            max_date += timedelta(days=30)
                        value = [min_date.strftime('%Y-%m-%d'), max_date.strftime('%Y-%m-%d')]
                    else:
                        value = [val1, val2]
                else:
                    value = self.get_field_value(field, field_type)
                
                rules.append({
                    "field": field,
                    "operator": operator,
                    "value": value
                })
            
            groups.append({
                "condition": random.choice(["AND", "OR"]),
                "rules": rules
            })
        
        return {
            "groups": groups,
            "group_logic": random.choice(["AND", "OR"]),
            "limit": random.choice([50, 100, 250, 500])
        }
    
    def generate_invalid_advanced_search(self) -> Dict[str, Any]:
        """Generate an INVALID advanced search payload to test error handling"""
        error_category = random.choice([
            "invalid_field_name",
            "invalid_property_name", 
            "wrong_operator_for_type",
            "wrong_value_type",
            "invalid_between_values",
            "invalid_group_logic",
            "invalid_condition",
            "invalid_limit",
            "missing_required",
            "empty_groups",
            "empty_rules"
        ])
        
        if error_category == "invalid_field_name":
            # Use invalid field name in rule
            return {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": [
                            {
                                "field": random.choice(INVALID_FIELD_NAMES),
                                "operator": "equals",
                                "value": "test"
                            }
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        
        elif error_category == "invalid_property_name":
            # Typo in property name
            return {
                "groupz": [  # Typo: groupz instead of groups
                    {
                        "condition": "AND",
                        "rules": [
                            {"field": "title", "operator": "equals", "value": "test"}
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        
        elif error_category == "wrong_operator_for_type":
            # Use numeric operator on string field or vice versa
            is_numeric_on_string = random.choice([True, False])
            
            if is_numeric_on_string:
                # Numeric operator on string field
                return {
                    "groups": [
                        {
                            "condition": "AND",
                            "rules": [
                                {
                                    "field": random.choice(STRING_FIELDS),
                                    "operator": random.choice(["gt", "lt", "gte", "lte", "between"]),
                                    "value": "string_value"
                                }
                            ]
                        }
                    ],
                    "group_logic": "AND",
                    "limit": 50
                }
            else:
                # String operator on numeric field
                return {
                    "groups": [
                        {
                            "condition": "AND",
                            "rules": [
                                {
                                    "field": random.choice(INTEGER_FIELDS),
                                    "operator": random.choice(["contains", "starts_with", "ends_with"]),
                                    "value": 12345
                                }
                            ]
                        }
                    ],
                    "group_logic": "AND",
                    "limit": 50
                }
        
        elif error_category == "wrong_value_type":
            # Submit wrong type for a field
            field = random.choice(ALL_SEARCHABLE_FIELDS)
            field_type = self.get_field_type(field)
            operator = "equals"
            
            return {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": [
                            {
                                "field": field,
                                "operator": operator,
                                "value": self.get_invalid_value(field, field_type)
                            }
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        
        elif error_category == "invalid_between_values":
            # Invalid between operator usage
            between_error = random.choice([
                "not_list",
                "wrong_count",
                "max_less_than_min",
                "invalid_types"
            ])
            
            if between_error == "not_list":
                value = 50  # Should be a list
            elif between_error == "wrong_count":
                value = [10, 20, 30]  # Should be exactly 2 values
            elif between_error == "max_less_than_min":
                value = [100, 10]  # min > max (invalid)
            else:  # invalid_types
                value = ["not", "numbers"]  # Strings for integer field
            
            return {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": [
                            {
                                "field": random.choice(INTEGER_FIELDS),
                                "operator": "between",
                                "value": value
                            }
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        
        elif error_category == "invalid_group_logic":
            return {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": [
                            {"field": "title", "operator": "equals", "value": "test"}
                        ]
                    }
                ],
                "group_logic": random.choice(INVALID_LOGIC),
                "limit": 50
            }
        
        elif error_category == "invalid_condition":
            return {
                "groups": [
                    {
                        "condition": random.choice(INVALID_LOGIC),
                        "rules": [
                            {"field": "title", "operator": "equals", "value": "test"}
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        
        elif error_category == "invalid_limit":
            return {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": [
                            {"field": "title", "operator": "equals", "value": "test"}
                        ]
                    }
                ],
                "group_logic": "AND",
                "limit": random.choice(INVALID_LIMITS)
            }
        
        elif error_category == "missing_required":
            missing_type = random.choice(["missing_groups", "missing_rule_field", "missing_group_field"])
            
            if missing_type == "missing_groups":
                # Missing top-level "groups"
                return {
                    "group_logic": "AND",
                    "limit": 50
                }
            elif missing_type == "missing_rule_field":
                # Missing required field in a rule
                rule = {"field": "title", "operator": "equals", "value": "test"}
                del rule[random.choice(["field", "operator", "value"])]
                
                return {
                    "groups": [
                        {
                            "condition": "AND",
                            "rules": [rule]
                        }
                    ],
                    "group_logic": "AND",
                    "limit": 50
                }
            else:  # missing_group_field
                # Missing "condition" or "rules" in a group
                group = {
                    "condition": "AND",
                    "rules": [{"field": "title", "operator": "equals", "value": "test"}]
                }
                del group[random.choice(["condition", "rules"])]
                
                return {
                    "groups": [group],
                    "group_logic": "AND",
                    "limit": 50
                }
        
        elif error_category == "empty_groups":
            return {
                "groups": [],
                "group_logic": "AND",
                "limit": 50
            }
        
        elif error_category == "empty_rules":
            return {
                "groups": [
                    {
                        "condition": "AND",
                        "rules": []
                    }
                ],
                "group_logic": "AND",
                "limit": 50
            }
        
        return {}
    
    def execute_search(self, endpoint: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Execute a search request and return success status and response"""
        try:
            response = requests.post(endpoint, json=payload, timeout=30)
            
            # For invalid tests, we EXPECT errors (4xx status codes)
            # For valid tests, we expect success (200)
            if self.test_type == "invalid":
                # Success means we got a validation error (400-499)
                success = 400 <= response.status_code < 500
            else:
                # Success means we got a 200 OK
                success = response.status_code == 200
            
            result = {
                "status_code": response.status_code,
                "response": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
            }
            
            return success, result
        
        except requests.exceptions.Timeout:
            return False, {"status_code": "TIMEOUT", "error": "Request timeout"}
        except requests.exceptions.ConnectionError:
            return False, {"status_code": "CONNECTION_ERROR", "error": "Connection error"}
        except Exception as e:
            return False, {"status_code": "ERROR", "error": str(e)}
    
    def run_test(self, test_num: int):
        """Run a single random test"""
        # Randomly choose endpoint
        use_simple = random.choice([True, False])
        endpoint = SIMPLE_ENDPOINT if use_simple else ADVANCED_ENDPOINT
        endpoint_name = "simple" if use_simple else "advanced"
        
        # Generate payload
        if use_simple:
            payload = self.generate_simple_search()
        else:
            payload = self.generate_advanced_search()
        
        # Execute search
        success, response = self.execute_search(endpoint, payload)
        
        # Record results
        test_result = {
            "test_number": test_num,
            "timestamp": datetime.now().isoformat(),
            "endpoint": endpoint,
            "endpoint_type": endpoint_name,
            "payload": payload,
            "response": response,
            "success": success
        }
        
        self.results["tests"].append(test_result)
        self.results["total_tests"] += 1
        
        if success:
            self.results["successes"] += 1
        else:
            self.results["failures"] += 1
    
    def run_all_tests(self):
        """Run all tests"""
        num_tests = random.randint(count_from, count_to)
        test_mode = "INVALID" if self.test_type == "invalid" else "VALID"
        csv_action = "OVERWRITING" if csv_mode == "overwrite" else "APPENDING TO"
        
        print(f"Running {num_tests} {test_mode} tests... ({csv_action} {self.log_filename})")
        
        for i in range(1, num_tests + 1):
            self.run_test(i)
            # Minimal progress indicator
            if i % 10 == 0:
                print(f"Progress: {i}/{num_tests} tests completed")
        
        # Save to CSV
        self.save_csv_log()
        
        # Minimal summary
        success_rate = (self.results['successes']/self.results['total_tests']*100)
        
        if self.test_type == "invalid":
            print(f"\nCompleted: {self.results['total_tests']} tests | "
                f"Validation Errors Caught: {self.results['successes']} | "
                f"Unexpected Success: {self.results['failures']} | "
                f"Error Detection Rate: {success_rate:.1f}%")
        else:
            print(f"\nCompleted: {self.results['total_tests']} tests | "
                f"Success: {self.results['successes']} | "
                f"Failed: {self.results['failures']} | "
                f"Rate: {success_rate:.1f}%")
            
    def save_csv_log(self):
        """Save results to CSV file"""
        # Determine if we need to write headers based on csv_mode
        write_headers = False
        
        if csv_mode == "overwrite":
            # Overwrite mode: always write headers
            file_mode = 'w'
            write_headers = True
        else:  # append mode
            # Append mode: only write headers if file doesn't exist
            try:
                with open(self.log_filename, 'r') as f:
                    file_mode = 'a'
                    write_headers = False
            except FileNotFoundError:
                file_mode = 'a'
                write_headers = True
        
        with open(self.log_filename, file_mode, newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header if needed
            if write_headers:
                writer.writerow([
                    'Test Type',
                    'Test #',
                    'Timestamp',
                    'Endpoint Type',
                    'Success',
                    'Status Code',
                    'Result Count',
                    'Fields Searched',
                    'Logic/Group Logic',
                    'Limit',
                    'Error Message',
                    'Request Summary',
                    'Response Summary',
                    'Request JSON',
                ])
            
            # Write test results
            for test in self.results['tests']:
                endpoint_type = test['endpoint_type']
                payload = test['payload']
                response = test['response']
                
                # Extract fields searched
                if endpoint_type == 'simple':
                    fields = ', '.join([f.get('field', 'INVALID') for f in payload.get('filters', [])])
                    logic = payload.get('logic', 'N/A')
                    request_summary = f"{len(payload.get('filters', []))} filters ({payload.get('rules', 'N/A')} mode)"
                else:  # advanced
                    all_fields = []
                    for group in payload.get('groups', []):
                        all_fields.extend([r.get('field', 'INVALID') for r in group.get('rules', [])])
                    fields = ', '.join(all_fields)
                    logic = payload.get('group_logic', 'N/A')
                    request_summary = f"{len(payload.get('groups', []))} groups, {sum(len(g.get('rules', [])) for g in payload.get('groups', []))} total rules"
                
                # Extract response details
                status_code = response.get('status_code', 'N/A')
                error_msg = ""
                
                # Extract error message from response
                if isinstance(response.get('response'), dict):
                    # FastAPI validation error format
                    if 'detail' in response['response']:
                        detail = response['response']['detail']
                        if isinstance(detail, list):
                            # Pydantic validation errors
                            error_msg = '; '.join([
                                f"{err.get('loc', ['unknown'])[-1]}: {err.get('msg', 'error')}"
                                for err in detail
                            ])
                        elif isinstance(detail, str):
                            error_msg = detail
                        else:
                            error_msg = str(detail)
                    elif 'error' in response['response']:
                        error_msg = response['response']['error']
                elif 'error' in response:
                    error_msg = response['error']
                
                if 'response' in response and isinstance(response['response'], dict):
                    result_count = response['response'].get('resultcount', 0)
                    if result_count > 0:
                        response_summary = f"{result_count} results"
                    elif error_msg:
                        response_summary = f"Error: {error_msg[:100]}"
                    else:
                        response_summary = "No results"
                elif error_msg:
                    result_count = 0
                    response_summary = f"Error: {error_msg[:100]}"
                else:
                    result_count = 0
                    response_summary = "Unknown response"
                
                # Single-line JSON (no pretty print)
                request_json = json.dumps(payload, separators=(',', ':'))
                
                # FAIL is always FAIL, regardless of test type
                if test['success']:
                    if self.test_type == "invalid":
                        # For invalid tests, success means we caught an error
                        pass_fail = 'PASS (Error Caught)'
                    else:
                        # For valid tests, success means we got results
                        pass_fail = 'PASS'
                else:
                    # Any failure is just FAIL - no special messaging
                    pass_fail = 'FAIL'
                
                # Write row
                writer.writerow([
                    self.test_type.upper(),
                    test['test_number'],
                    test['timestamp'],
                    endpoint_type.upper(),
                    pass_fail,
                    status_code,
                    result_count,
                    fields,
                    logic,
                    payload.get('limit', 'N/A'),
                    error_msg,
                    request_summary,
                    response_summary,
                    request_json,
                ])
            
def main():
    """Main entry point"""
    test_mode = "INVALID DATA (ERROR TESTING)" if test_type == "invalid" else "VALID DATA"
    print("="*60)
    print("SEARCH ENDPOINT TESTER")
    print(f"Mode: {test_mode}")
    print(f"Target: {BASE_URL}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    tester = SearchTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()