from typing import Dict, Any, Optional
from utils_warning_parser import parse_warning_message


def enrich_with_warning_components(full_data_clean: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich full_data_clean with parsed warning components.
    
    This function:
    1. Extracts the warning_message field
    2. Parses it into structured components
    3. Adds a new 'warning_components' section to full_data_clean
    
    Args:
        full_data_clean: The cleaned FBI data dictionary
        
    Returns:
        Enhanced dictionary with warning_components added
    """
    warning_text = full_data_clean.get('warning_message')
    
    # Parse warning message into components
    components = parse_warning_message(warning_text)
    
    # Calculate danger score
    danger_score = calculate_danger_score(components)
    
    # Add warning_components section to full_data_clean
    full_data_clean['warning_components'] = {
        'armed_level': components['warning_armed_level'],
        'flight_risk': components['warning_flight_risk'],
        'international_flight': components['warning_international_flight'],
        'escape_risk': components['warning_escape_risk'],
        'international_escape': components['warning_international_escape'],
        'violent_tendencies': components['warning_violent_tendencies'],
        'suicide_risk': components['warning_suicide_risk'],
        'bipolar': components['warning_bipolar'],
        'drug_abuse': components['warning_drug_abuse'],
        'high_risk_arrest': components['warning_high_risk_arrest'],
        'multiple_subjects': components['warning_multiple_subjects'],
        'danger_score': danger_score
    }
    
    return full_data_clean


def calculate_danger_score(components: Dict[str, Any]) -> int:
    """
    Calculate danger score from warning components.
    
    Scoring algorithm:
    - Armed Level: 0-4 points (NONE=0, DANGEROUS=2, ARMED_DANGEROUS=3, ARMED_EXTREMELY_DANGEROUS=4)
    - Each risk flag: 1 point
    - Violent tendencies: 2 points
    - Other behavioral flags: 1 point each
    
    Returns:
        Danger score (0-10 range)
    """
    score = 0
    
    # Armed level points (0-4)
    armed_level = components.get('warning_armed_level', 'NONE')
    if armed_level == 'ARMED_EXTREMELY_DANGEROUS':
        score += 4
    elif armed_level == 'ARMED_DANGEROUS':
        score += 3
    elif armed_level == 'DANGEROUS':
        score += 2
    
    # Risk flags (1 point each)
    if components.get('warning_flight_risk'):
        score += 1
    if components.get('warning_international_flight'):
        score += 1
    if components.get('warning_escape_risk'):
        score += 1
    
    # Behavioral flags
    if components.get('warning_violent_tendencies'):
        score += 2  # Violent tendencies weighted higher
    if components.get('warning_suicide_risk'):
        score += 1
    if components.get('warning_high_risk_arrest'):
        score += 1
    
    return score


def get_warning_summary(components: Dict[str, Any]) -> str:
    """
    Generate a human-readable warning summary from components.
    
    Args:
        components: Dictionary of warning components from parse_warning_message()
        
    Returns:
        Human-readable summary string
    """
    if not components or components.get('warning_armed_level') == 'NONE':
        return "No warning"
    
    parts = []
    
    # Armed level
    armed_level = components.get('warning_armed_level', 'NONE')
    if armed_level == 'ARMED_EXTREMELY_DANGEROUS':
        parts.append("Armed & Extremely Dangerous")
    elif armed_level == 'ARMED_DANGEROUS':
        parts.append("Armed & Dangerous")
    elif armed_level == 'DANGEROUS':
        parts.append("Dangerous")
    
    # Flight/escape risks
    if components.get('warning_international_flight'):
        parts.append("International Flight Risk")
    elif components.get('warning_flight_risk'):
        parts.append("Flight Risk")
    
    if components.get('warning_international_escape'):
        parts.append("International Escape Risk")
    elif components.get('warning_escape_risk'):
        parts.append("Escape Risk")
    
    # Behavioral flags
    if components.get('warning_violent_tendencies'):
        parts.append("Violent Tendencies")
    if components.get('warning_suicide_risk'):
        parts.append("Suicide Risk")
    if components.get('warning_bipolar'):
        parts.append("Bi-polar")
    if components.get('warning_drug_abuse'):
        parts.append("Drug Abuse")
    if components.get('warning_high_risk_arrest'):
        parts.append("High-Risk Arrest")
    
    return ", ".join(parts) if parts else "No warning"
