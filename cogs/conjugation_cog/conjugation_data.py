"""
Conjugation data for Spanish verbs - loaded from parsed XML data
"""

import json
import random
import os

# Load the parsed verb data
def load_verbs_data():
    """Load verb data from the XML parser directly"""
    try:
        from .xml_parser import SpanishVerbParser
    except ImportError:
        # Handle case when running as script (not as module)
        from xml_parser import SpanishVerbParser
    import os
    
    # Initialize parser with XML data
    verbs_xml = os.path.join(os.path.dirname(__file__), 'data', 'verbs-es.xml')
    conjugations_xml = os.path.join(os.path.dirname(__file__), 'data', 'conjugations-es.xml')
    
    try:
        parser = SpanishVerbParser(verbs_xml, conjugations_xml)
        parser.parse_conjugation_templates()
        parser.parse_verbs()
        return parser.get_common_verbs(200)
    except Exception as e:
        print(f"Warning: Failed to load verb data from XML: {e}. Using fallback data.")
        return FALLBACK_VERBS

# Fallback data in case JSON file is not available
FALLBACK_VERBS = [
    {
        "infinitive": "hablar",
        "conjugations": {
            "presente": {
                "yo": "hablo",
                "tú": "hablas",
                "él/ella": "habla",
                "nosotros": "hablamos",
                "vosotros": "habláis",
                "ellos/ellas": "hablan"
            }
        },
        "difficulty": "beginner"
    },
    {
        "infinitive": "ser",
        "conjugations": {
            "presente": {
                "yo": "soy",
                "tú": "eres",
                "él/ella": "es",
                "nosotros": "somos",
                "vosotros": "sois",
                "ellos/ellas": "son"
            }
        },
        "difficulty": "intermediate"
    }
]

# Load the verb data
VERBS_DATA = load_verbs_data()

def get_random_verb():
    """Get a random verb from the data"""
    return random.choice(VERBS_DATA)

def get_all_verbs():
    """Get all available verbs"""
    return VERBS_DATA

def get_verbs_by_difficulty(difficulty="beginner"):
    """Get verbs filtered by difficulty level"""
    return [verb for verb in VERBS_DATA if verb.get('difficulty', 'beginner') == difficulty]
