"""
Array Cleaning Utilities for BOLO ETL Processing

This module provides functions to clean and standardize array data before
insertion into PostgreSQL text[] columns.

Target format: {element1, element2} - clean format without embedded quotes
"""

import re
from typing import List, Optional, Any


def clean_array_element(element: Any) -> Optional[str]:
    """
    Clean a single array element by:
    - Converting to string
    - Removing embedded double quotes
    - Removing escaped quotes
    - Normalizing whitespace
    - Stripping HTML/control characters
    
    Args:
        element: The array element to clean
        
    Returns:
        Cleaned string or None if element is empty/None
    """
    if element is None:
        return None
    
    # Convert to string
    text = str(element)
    
    # Remove various quote patterns
    # Pattern 1: Escaped double quotes \"text\"
    text = re.sub(r'\\"', '', text)
    
    # Pattern 2: Regular double quotes around or within text
    text = text.replace('"', '')
    
    # Pattern 3: Curly/smart quotes
    text = re.sub(r'[\u201C\u201D\u201E\u201F]', '', text)  # Double smart quotes
    text = re.sub(r'[\u2018\u2019\u201A\u201B]', "'", text)  # Single smart quotes -> apostrophe
    
    # Remove control characters (keep normal whitespace)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
    
    # Remove basic HTML tags
    text = re.sub(r'</?(?:p|br|b|i|u|strong|em|span|div)(?:\s[^>]*)?>',  '', text, flags=re.IGNORECASE)
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    # Return None for empty strings
    return text if text else None


def clean_array(arr: Optional[List[Any]]) -> Optional[List[str]]:
    """
    Clean an entire array by processing each element.
    
    Args:
        arr: List of elements to clean
        
    Returns:
        List of cleaned strings, or None if input is None/empty
    """
    if arr is None:
        return None
    
    if not isinstance(arr, list):
        return None
    
    # Clean each element and filter out None/empty values
    cleaned = []
    for item in arr:
        clean_item = clean_array_element(item)
        if clean_item:
            cleaned.append(clean_item)
    
    # Return None for empty lists (consistent with PostgreSQL NULL)
    return cleaned if cleaned else None


def extract_and_clean_array(data: dict, field: str) -> Optional[List[str]]:
    """
    Extract array field from dict and clean it.
    This is the main function to use during ETL processing.
    
    Args:
        data: Dictionary containing the field
        field: Name of the array field to extract
        
    Returns:
        Cleaned list of strings, or None
    """
    value = data.get(field)
    return clean_array(value)


def format_array_for_display(arr: Optional[List[str]]) -> str:
    """
    Format a cleaned array for display/logging purposes.
    Shows the PostgreSQL-style representation.
    
    Args:
        arr: Cleaned array
        
    Returns:
        String representation like {element1, element2}
    """
    if arr is None or not arr:
        return 'NULL'
    
    # PostgreSQL array literal format
    return '{' + ', '.join(arr) + '}'


# Example usage and testing
if __name__ == "__main__":
    # Test cases representing the variations you mentioned
    test_cases = [
        # Case 1: Clean format (already good)
        ["element1", "element2"],
        
        # Case 2: Elements with embedded double quotes
        ['"element1"', '"element2"'],
        
        # Case 3: Escaped double quotes
        ['\\"element1\\"', '\\"element2\\"'],
        
        # Case 4: Mixed mess
        ['"\\"John \\"The Beast\\" Smith\\""', 'Regular Name'],
        
        # Case 5: With smart quotes and HTML
        ['\u201CQuoted Name\u201D', '<b>Bold Text</b>'],
        
        # Case 6: With empty/whitespace elements
        ['Valid', '', '   ', None, 'Also Valid'],
    ]
    
    print("Array Cleaning Test Results")
    print("=" * 60)
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}:")
        print(f"  Input:  {test}")
        cleaned = clean_array(test)
        print(f"  Output: {cleaned}")
        print(f"  Format: {format_array_for_display(cleaned)}")
