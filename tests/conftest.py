"""Shared source vaccine mapping for preparation boundary checks."""

import pytest


@pytest.fixture
def default_vaccine_reference() -> dict[str, list]:
    """Provide a minimal vaccine reference for testing.

    Real-world significance:
    - Maps vaccine codes to component diseases
    - Used by preprocess to expand vaccine records into diseases
    - Affects disease coverage text in notices

    Returns
    -------
    Dict[str, list]
        Maps vaccine codes to disease components, e.g. {"DTaP": ["Diphtheria", "Tetanus", "Pertussis"]}
    """
    return {
        "DTaP": ["Diphtheria", "Tetanus", "Pertussis"],
        "IPV": ["Polio"],
        "MMR": ["Measles", "Mumps", "Rubella"],
        "Varicella": ["Chickenpox"],
        "MenC": ["Meningococcal"],
        "PCV": ["Pneumococcal"],
        "Hib": ["Haemophilus influenzae"],
        "HBV": ["Hepatitis B"],
        "HPV": ["Human Papillomavirus"],
    }
