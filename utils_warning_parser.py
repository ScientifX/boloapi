import re
from typing import Dict, Optional


def parse_warning_message(warning_text: Optional[str]) -> Dict[str, any]:
    """
    Parse an FBI warning message into structured components.
    
    Args:
        warning_text: Original warning message text (can be None)
        
    Returns:
        Dictionary with normalized warning components
    """
    if not warning_text:
        return {
            'warning_armed_level': None,
            'warning_flight_risk': False,
            'warning_international_flight': False,
            'warning_escape_risk': False,
            'warning_international_escape': False,
            'warning_violent_tendencies': False,
            'warning_suicide_risk': False,
            'warning_bipolar': False,
            'warning_drug_abuse': False,
            'warning_high_risk_arrest': False,
            'warning_multiple_subjects': False
        }
    
    # Normalize text for parsing
    text_upper = warning_text.upper().strip()
    
    # Initialize result dictionary
    result = {
        'warning_armed_level': 'NONE',
        'warning_flight_risk': False,
        'warning_international_flight': False,
        'warning_escape_risk': False,
        'warning_international_escape': False,
        'warning_violent_tendencies': False,
        'warning_suicide_risk': False,
        'warning_bipolar': False,
        'warning_drug_abuse': False,
        'warning_high_risk_arrest': False,
        'warning_multiple_subjects': False
    }
    
    # Detect multiple subjects
    if 'THESE INDIVIDUALS' in text_upper:
        result['warning_multiple_subjects'] = True
    
    # Parse armed status (ordered by severity - most severe first)
    if 'ARMED AND EXTREMELY DANGEROUS' in text_upper:
        result['warning_armed_level'] = 'ARMED_EXTREMELY_DANGEROUS'
    elif 'ARMED AND DANGEROUS' in text_upper:
        result['warning_armed_level'] = 'ARMED_DANGEROUS'
    elif 'SHOULD BE CONSIDERED DANGEROUS' in text_upper:
        result['warning_armed_level'] = 'DANGEROUS'
    else:
        result['warning_armed_level'] = 'NONE'
    
    # Parse flight/escape risks
    # Check international first (more specific)
    if 'INTERNATIONAL FLIGHT RISK' in text_upper:
        result['warning_international_flight'] = True
        result['warning_flight_risk'] = True  # International implies general flight risk
    elif 'FLIGHT RISK' in text_upper:
        result['warning_flight_risk'] = True
    
    if 'INTERNATIONAL ESCAPE RISK' in text_upper:
        result['warning_international_escape'] = True
        result['warning_escape_risk'] = True  # International implies general escape risk
    elif 'ESCAPE RISK' in text_upper:
        result['warning_escape_risk'] = True
    
    # Parse behavioral/mental health flags
    if 'VIOLENT TENDENCIES' in text_upper or 'MAY HAVE VIOLENT TENDENCIES' in text_upper:
        result['warning_violent_tendencies'] = True
    
    if 'SUICIDE RISK' in text_upper or 'SUICIDAL TENDENCIES' in text_upper:
        result['warning_suicide_risk'] = True
    
    if 'BI-POLAR' in text_upper or 'MAY BE IN NEED OF MEDICATIONS' in text_upper:
        result['warning_bipolar'] = True
    
    if 'KNOWN TO ABUSE DRUGS' in text_upper:
        result['warning_drug_abuse'] = True
    
    if 'HIGH-RISK ARREST' in text_upper:
        result['warning_high_risk_arrest'] = True
    
    return result


def reconstruct_warning_message(components: Dict[str, any]) -> str:
    """
    Reconstruct a standardized warning message from components.
    Useful for displaying consistent warning text to users.
    
    Args:
        components: Dictionary of warning components from parse_warning_message()
        
    Returns:
        Human-readable warning message
    """
    parts = []
    
    # Subject prefix
    if components.get('warning_multiple_subjects'):
        prefix = "These individuals should be considered"
    else:
        prefix = "Should be considered"
    
    # Armed status
    armed = components.get('warning_armed_level', 'NONE')
    if armed == 'ARMED_EXTREMELY_DANGEROUS':
        parts.append("armed and extremely dangerous")
    elif armed == 'ARMED_DANGEROUS':
        parts.append("armed and dangerous")
    elif armed == 'DANGEROUS':
        parts.append("dangerous")
    
    # Risk types
    risks = []
    if components.get('warning_international_flight'):
        risks.append("an international flight risk")
    elif components.get('warning_flight_risk'):
        risks.append("a flight risk")
    
    if components.get('warning_international_escape'):
        risks.append("an international escape risk")
    elif components.get('warning_escape_risk'):
        risks.append("an escape risk")
    
    if risks:
        parts.extend(risks)
    
    # Behavioral flags
    if components.get('warning_violent_tendencies'):
        parts.append("may have violent tendencies")
    
    if components.get('warning_suicide_risk'):
        parts.append("a suicide risk")
    
    if components.get('warning_bipolar'):
        parts.append("bi-polar and may be in need of medications")
    
    if components.get('warning_drug_abuse'):
        parts.append("known to abuse drugs")
    
    if components.get('warning_high_risk_arrest'):
        parts.append("a high-risk arrest")
    
    # Construct final message
    if not parts:
        return ""
    
    # Join all parts with commas and 'and' before last item
    if len(parts) == 1:
        return f"{prefix} {parts[0]}"
    elif len(parts) == 2:
        return f"{prefix} {parts[0]} and {parts[1]}"
    else:
        return f"{prefix} {', '.join(parts[:-1])}, and {parts[-1]}"

