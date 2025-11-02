#!/usr/bin/env python3
"""
Random Search Endpoint Tester
Tests /simple and /advanced search endpoints with random but valid payloads
"""

import json
import random
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple
import sys
import csv

# Configuration
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

# Sample values for fields not in test_values.txt
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


class SearchTester:
    def __init__(self):
        self.results = {
            "total_tests": 0,
            "successes": 0,
            "failures": 0,
            "tests": []
        }
        self.log_filename = "search_test_log.csv"
    
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
    
    def generate_advanced_search(self) -> Dict[str, Any]:
        """Generate a random advanced search payload"""
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
    
    def execute_search(self, endpoint: str, payload: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Execute a search request and return success status and response"""
        try:
            response = requests.post(endpoint, json=payload, timeout=30)
            
            # Consider 200 as success, anything else as failure
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
        num_tests = random.randint(10000, 10000)
        print(f"Running {num_tests} tests... (log: {self.log_filename})")
        
        for i in range(1, num_tests + 1):
            self.run_test(i)
            # Minimal progress indicator
            if i % 10 == 0:
                print(f"Progress: {i}/{num_tests} tests completed")
        
        # Save to CSV
        self.save_csv_log()
        
        # Minimal summary
        success_rate = (self.results['successes']/self.results['total_tests']*100)
        print(f"\nCompleted: {self.results['total_tests']} tests | "
              f"Success: {self.results['successes']} | "
              f"Failed: {self.results['failures']} | "
              f"Rate: {success_rate:.1f}%")
    
    def save_csv_log(self):
        """Save results to CSV file"""
        # Check if file exists to determine if we need to write headers
        file_exists = False
        try:
            with open(self.log_filename, 'r') as f:
                file_exists = True
        except FileNotFoundError:
            file_exists = False
        
        with open(self.log_filename, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header only if file doesn't exist
            if not file_exists:
                writer.writerow([
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
                    # 'Response JSON'
                ])
            
            # Write test results
            for test in self.results['tests']:
                endpoint_type = test['endpoint_type']
                payload = test['payload']
                response = test['response']
                
                # Extract fields searched
                if endpoint_type == 'simple':
                    fields = ', '.join([f['field'] for f in payload['filters']])
                    logic = payload['logic']
                    request_summary = f"{len(payload['filters'])} filters ({payload['rules']} mode)"
                else:  # advanced
                    all_fields = []
                    for group in payload['groups']:
                        all_fields.extend([r['field'] for r in group['rules']])
                    fields = ', '.join(all_fields)
                    logic = payload['group_logic']
                    request_summary = f"{len(payload['groups'])} groups, {sum(len(g['rules']) for g in payload['groups'])} total rules"
                
                # Extract response details
                status_code = response.get('status_code', 'N/A')
                error_msg = response.get('error', '')
                
                if 'response' in response and isinstance(response['response'], dict):
                    result_count = response['response'].get('resultcount', 0)
                    response_summary = f"{result_count} results"
                elif error_msg:
                    result_count = 0
                    response_summary = f"Error: {error_msg}"
                else:
                    result_count = 0
                    response_summary = "Unknown response"
                
                # Pretty-print JSON for request and response
                request_json = json.dumps(payload, indent=2)
                response_json = json.dumps(response, indent=2)
                
                # Write row
                writer.writerow([
                    test['test_number'],
                    test['timestamp'],
                    endpoint_type.upper(),
                    'PASS' if test['success'] else 'FAIL',
                    status_code,
                    result_count,
                    fields,
                    logic,
                    payload.get('limit', 'N/A'),
                    error_msg,
                    request_summary,
                    response_summary,
                    request_json,
                    # response_json
                ])


def main():
    """Main entry point"""
    print("="*60)
    print("SEARCH ENDPOINT TESTER")
    print(f"Target: {BASE_URL}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    tester = SearchTester()
    tester.run_all_tests()


if __name__ == "__main__":
    main()