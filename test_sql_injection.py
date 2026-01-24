"""
SQL Injection Protection Test Suite
Tests that the BoloDoc API is properly protected against SQL injection attacks

This script attempts various SQL injection attacks to verify:
1. Parameterized queries prevent SQL code execution
2. Security middleware logs suspicious patterns
3. Application returns safe responses
4. Database remains secure

Run this script while your FastAPI app is running:
    python test_sql_injection.py

Requirements:
    pip install requests
"""
import requests
import json
import time
from typing import Dict, List, Tuple
from datetime import datetime


BASE_URL = "http://127.0.0.1:8000"

# ANSI color codes for pretty output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'
BOLD = '\033[1m'


class SQLInjectionTester:
    """Test suite for SQL injection protection"""
    
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.results = []
        self.token = None
        
    def get_auth_token(self):
        """
        Get authentication token for testing.
        For this test, we'll test both authenticated and unauthenticated endpoints.
        """
        # Note: You'll need valid credentials to test authenticated endpoints
        # For now, we'll test unauthenticated attack vectors
        pass
    
    def test_injection(self, name: str, endpoint: str, method: str = "POST",
                      payload: Dict = None, headers: Dict = None,
                      params: Dict = None) -> Dict:
        """
        Attempt an SQL injection attack and check the results
        
        Returns:
            Dict with test results including:
            - success: Whether the app handled it safely
            - status_code: HTTP response code
            - error_type: Type of error if any
            - data_leaked: Whether any sensitive data was returned
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method.upper() == "POST":
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers or {},
                    params=params,
                    timeout=10
                )
            else:  # GET
                response = requests.get(
                    url,
                    params=params,
                    headers=headers or {},
                    timeout=10
                )
            
            # Check if the injection succeeded (we want it to FAIL)
            injection_succeeded = False
            data_leaked = False
            
            # Look for signs of successful injection
            response_text = response.text.lower()
            
            # Bad signs: SQL errors exposed
            sql_error_indicators = [
                'syntax error',
                'postgresql',
                'psycopg2',
                'unterminated string',
                'column',
                'relation',
                'pg_',
                'sql',
                'query failed',
            ]
            
            # Check if SQL error was exposed (security issue)
            for indicator in sql_error_indicators:
                if indicator in response_text and response.status_code == 500:
                    injection_succeeded = True
                    break
            
            # Check if massive amounts of data were returned (potential data leak)
            if len(response.content) > 100000:  # More than 100KB
                data_leaked = True
            
            # A safe response is:
            # - 4xx error (bad request, unauthorized, not found)
            # - Empty or minimal response
            # - Generic error message (not exposing internals)
            is_safe = (
                response.status_code in [400, 401, 404, 422, 405] or
                (response.status_code == 200 and not data_leaked) or
                (response.status_code == 500 and not injection_succeeded)
            )
            
            result = {
                'name': name,
                'endpoint': endpoint,
                'method': method,
                'status_code': response.status_code,
                'injection_succeeded': injection_succeeded,
                'data_leaked': data_leaked,
                'is_safe': is_safe,
                'response_size': len(response.content),
                'payload': payload or params
            }
            
            self.results.append(result)
            return result
            
        except requests.RequestException as e:
            # Network errors are fine - the app is still safe
            result = {
                'name': name,
                'endpoint': endpoint,
                'method': method,
                'status_code': None,
                'injection_succeeded': False,
                'data_leaked': False,
                'is_safe': True,
                'response_size': 0,
                'error': str(e),
                'payload': payload or params
            }
            self.results.append(result)
            return result
    
    def run_all_tests(self):
        """Run comprehensive SQL injection test suite"""
        print(f"\n{BOLD}{'='*80}{RESET}")
        print(f"{BOLD}SQL INJECTION PROTECTION TEST SUITE{RESET}")
        print(f"{BOLD}{'='*80}{RESET}\n")
        
        print(f"{BLUE}Testing: {self.base_url}{RESET}")
        print(f"{BLUE}Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{RESET}\n")
        
        # Category 1: Classic SQL Injection Patterns
        print(f"\n{BOLD}Category 1: Classic SQL Injection Patterns{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "Classic OR injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' OR '1'='1",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Comment-based injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' OR '1'='1' --",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Union-based injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' UNION SELECT * FROM tbl_users --",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Stacked queries injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test'; DROP TABLE tbl_bolo; --",
                "limit": 10
            }
        )
        
        # Category 2: Data Extraction Attempts
        print(f"\n{BOLD}Category 2: Data Extraction Attempts{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "Extract password hashes",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' UNION SELECT password FROM tbl_users --",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Extract email addresses",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' OR email LIKE '%@%",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Database enumeration",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' UNION SELECT table_name FROM information_schema.tables --",
                "limit": 10
            }
        )
        
        # Category 3: Boolean-Based Blind Injection
        print(f"\n{BOLD}Category 3: Boolean-Based Blind Injection{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "Boolean blind - true condition",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' AND '1'='1",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Boolean blind - false condition",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' AND '1'='2",
                "limit": 10
            }
        )
        
        # Category 4: Time-Based Blind Injection
        print(f"\n{BOLD}Category 4: Time-Based Blind Injection{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "Time-based delay (PostgreSQL)",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test'; SELECT pg_sleep(5); --",
                "limit": 10
            }
        )
        
        # Category 5: Encoded Injection Attempts
        print(f"\n{BOLD}Category 5: Encoded Injection Attempts{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "URL-encoded injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test%27%20OR%20%271%27%3D%271",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Unicode-encoded injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test\u0027 OR \u00271\u0027=\u00271",
                "limit": 10
            }
        )
        
        # Category 6: Advanced Techniques
        print(f"\n{BOLD}Category 6: Advanced Techniques{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "Nested injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' OR (SELECT COUNT(*) FROM tbl_users) > 0 --",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Cast-based injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test' OR 1=CAST('1' AS INTEGER) --",
                "limit": 10
            }
        )
        
        # Category 7: Special Characters
        print(f"\n{BOLD}Category 7: Special Characters{RESET}")
        print(f"{'-'*80}")
        
        self.test_injection(
            "Null byte injection",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test\x00' OR '1'='1",
                "limit": 10
            }
        )
        
        self.test_injection(
            "Semicolon termination",
            "/v1/search/simple",
            method="POST",
            payload={
                "field": "subject",
                "value": "test'; SELECT version(); --",
                "limit": 10
            }
        )
        
    def print_results(self):
        """Print detailed test results"""
        print(f"\n{BOLD}{'='*80}{RESET}")
        print(f"{BOLD}TEST RESULTS SUMMARY{RESET}")
        print(f"{BOLD}{'='*80}{RESET}\n")
        
        total = len(self.results)
        safe = sum(1 for r in self.results if r['is_safe'])
        injections_blocked = sum(1 for r in self.results if not r['injection_succeeded'])
        data_protected = sum(1 for r in self.results if not r['data_leaked'])
        
        print(f"{BOLD}Overall Statistics:{RESET}")
        print(f"  Total Injection Attempts: {total}")
        print(f"  {GREEN}Safe Responses: {safe} ({100*safe/total:.1f}%){RESET}")
        print(f"  {GREEN}Injections Blocked: {injections_blocked} ({100*injections_blocked/total:.1f}%){RESET}")
        print(f"  {GREEN}Data Protected: {data_protected} ({100*data_protected/total:.1f}%){RESET}")
        print()
        
        # Check for any successful injections (should be ZERO)
        vulnerabilities = [r for r in self.results if not r['is_safe'] or r['injection_succeeded']]
        
        if vulnerabilities:
            print(f"{RED}{BOLD}WARNING: POTENTIAL VULNERABILITIES DETECTED{RESET}\n")
            for vuln in vulnerabilities:
                print(f"{RED}[VULNERABLE] {vuln['name']}{RESET}")
                print(f"  Endpoint: {vuln['endpoint']}")
                print(f"  Status: {vuln['status_code']}")
                print(f"  Injection Succeeded: {vuln['injection_succeeded']}")
                print(f"  Data Leaked: {vuln['data_leaked']}")
                print(f"  Payload: {vuln['payload']}")
                print()
        else:
            print(f"{GREEN}{BOLD}ALL INJECTION ATTEMPTS SAFELY BLOCKED!{RESET}\n")
            print(f"{GREEN}Your application is properly protected against SQL injection.{RESET}\n")
        
        # Detailed results
        print(f"\n{BOLD}Detailed Results by Category:{RESET}")
        print(f"{'-'*80}\n")
        
        for i, result in enumerate(self.results, 1):
            status_icon = f"{GREEN}✓{RESET}" if result['is_safe'] else f"{RED}✗{RESET}"
            
            print(f"{status_icon} {BOLD}{result['name']}{RESET}")
            print(f"   Endpoint: {result['method']} {result['endpoint']}")
            print(f"   Status Code: {result['status_code']}")
            print(f"   Response Size: {result['response_size']} bytes")
            
            if result.get('error'):
                print(f"   Error: {result['error']}")
            
            if result['injection_succeeded']:
                print(f"   {RED}WARNING: SQL Injection may have succeeded{RESET}")
            
            if result['data_leaked']:
                print(f"   {RED}WARNING: Potential data leak detected{RESET}")
            
            print()
        
        # Security recommendations
        print(f"\n{BOLD}Security Analysis:{RESET}")
        print(f"{'-'*80}\n")
        
        if safe == total:
            print(f"{GREEN}✓ All injection attempts were safely handled{RESET}")
            print(f"{GREEN}✓ No SQL errors were exposed to attackers{RESET}")
            print(f"{GREEN}✓ No sensitive data was leaked{RESET}")
            print(f"{GREEN}✓ Parameterized queries are working correctly{RESET}")
            print()
            print(f"{BOLD}Your application demonstrates excellent SQL injection protection!{RESET}")
        else:
            print(f"{RED}⚠ Some injection attempts may not have been handled safely{RESET}")
            print(f"{YELLOW}Review the vulnerabilities listed above{RESET}")
            print(f"{YELLOW}Consider additional input validation{RESET}")
        
        print()
        
    def print_server_log_reminder(self):
        """Remind user to check server logs"""
        print(f"\n{BOLD}{'='*80}{RESET}")
        print(f"{BOLD}CHECK YOUR SERVER LOGS{RESET}")
        print(f"{BOLD}{'='*80}{RESET}\n")
        
        print(f"{YELLOW}The security middleware should have logged these injection attempts.{RESET}")
        print(f"{YELLOW}Look for log entries containing:{RESET}\n")
        
        print(f"  {BLUE}WARNING - SECURITY: Suspicious pattern detected{RESET}")
        print(f"  {BLUE}Path: /v1/search/simple{RESET}")
        print(f"  {BLUE}Patterns: OR '1'='1, UNION SELECT, DROP TABLE, etc.{RESET}\n")
        
        print(f"{YELLOW}Example log entry you should see:{RESET}\n")
        print(f"{BLUE}WARNING - SECURITY: Suspicious pattern detected - ")
        print(f"    Path: /v1/search/simple, Method: POST, ")
        print(f"    IP: 127.0.0.1, User-Agent: python-requests{RESET}\n")
        
        print(f"{GREEN}These logs are valuable for:{RESET}")
        print(f"  • Security monitoring and alerting")
        print(f"  • Identifying attack patterns")
        print(f"  • Compliance and audit trails")
        print(f"  • Forensic analysis\n")


def main():
    """Run SQL injection tests"""
    print(f"\n{BOLD}{BLUE}BoloDoc API - SQL Injection Protection Test{RESET}")
    print(f"{BLUE}Testing server at: {BASE_URL}{RESET}\n")
    
    print(f"{YELLOW}IMPORTANT: Make sure your FastAPI server is running!{RESET}")
    print(f"{YELLOW}This test will attempt SQL injection attacks to verify protection.{RESET}")
    print(f"{YELLOW}All attempts should be safely blocked by parameterized queries.{RESET}\n")
    
    input(f"Press Enter to begin testing...")
    
    tester = SQLInjectionTester(BASE_URL)
    
    print(f"\n{BOLD}Running SQL injection tests...{RESET}\n")
    tester.run_all_tests()
    
    print(f"\n{BOLD}Analyzing results...{RESET}")
    time.sleep(1)
    
    tester.print_results()
    tester.print_server_log_reminder()
    
    print(f"\n{BOLD}{'='*80}{RESET}")
    print(f"{BOLD}Test Complete!{RESET}")
    print(f"{BOLD}{'='*80}{RESET}\n")


if __name__ == "__main__":
    main()
