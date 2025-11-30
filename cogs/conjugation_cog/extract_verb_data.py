"""
Extract clean verb data for the simplified conjugation game
Generates a JSON file with just the verbs and tenses we need
"""

import json
import os
from xml_parser import SpanishVerbParser

# Define our categories
CATEGORIES = {
    "high-frequency": {
        "name": "High Frequency Verbs",
        "description": "Top 30 most common Spanish verbs",
        "verbs": [
            "ser", "estar", "tener", "hacer", "poder", "decir", "ir", "ver",
            "dar", "saber", "querer", "llegar", "pasar", "deber", "poner",
            "parecer", "quedar", "creer", "hablar", "llevar", "dejar", "seguir",
            "encontrar", "llamar", "venir", "pensar", "salir", "volver", "tomar", "conocer"
        ],
        "tenses": ["presente", "pretérito", "futuro"]
    },
    "regular-ar": {
        "name": "Regular -AR Verbs",
        "description": "Practice regular -ar verb patterns",
        "verbs": [
            "hablar", "llegar", "pasar", "quedar", "llevar", "dejar", "llamar",
            "trabajar", "estudiar", "tomar", "mirar", "escuchar", "bailar",
            "cantar", "comprar", "cocinar", "buscar", "caminar", "esperar", "preguntar"
        ],
        "tenses": ["presente", "pretérito", "futuro"]
    },
    "regular-er-ir": {
        "name": "Regular -ER/-IR Verbs",
        "description": "Practice regular -er and -ir verb patterns",
        "verbs": [
            "comer", "beber", "aprender", "creer", "leer", "vender", "correr",
            "vivir", "escribir", "recibir", "abrir", "decidir", "permitir",
            "sufrir", "subir", "dividir", "discutir"
        ],
        "tenses": ["presente", "pretérito", "futuro"]
    },
    "irregulars": {
        "name": "Common Irregular Verbs",
        "description": "Essential irregular verbs everyone needs to know",
        "verbs": [
            "ser", "estar", "ir", "tener", "hacer", "poder", "decir",
            "venir", "poner", "saber", "querer", "dar", "ver", "salir", "traer"
        ],
        "tenses": ["presente", "pretérito", "futuro"]
    }
}

# Tense mapping: our simple names -> XML names
TENSE_MAPPING = {
    "presente": ("indicativo", "presente"),
    "pretérito": ("indicativo", "pretérito-perfecto-simple"),
    "futuro": ("indicativo", "futuro")
}

def extract_verb_data():
    """Extract verb conjugations from XML data"""

    # Initialize parser
    cog_dir = os.path.dirname(__file__)
    verbs_xml = os.path.join(cog_dir, 'data', 'verbs-es.xml')
    conjugations_xml = os.path.join(cog_dir, 'data', 'conjugations-es.xml')

    parser = SpanishVerbParser(verbs_xml, conjugations_xml)
    parser.parse_conjugation_templates()
    parser.parse_verbs()

    # Load frequency data for English translations
    frequency_file = os.path.join(cog_dir, 'data', '200_common_verbs.json')
    with open(frequency_file, 'r', encoding='utf-8') as f:
        frequency_data = json.load(f)

    # Create lookup for English translations
    english_lookup = {v['infinitive']: v['english'] for v in frequency_data}

    # Extract data
    output_data = {
        "categories": {},
        "verbs": {}
    }

    # Process each category
    for cat_id, cat_info in CATEGORIES.items():
        output_data["categories"][cat_id] = {
            "name": cat_info["name"],
            "description": cat_info["description"],
            "verbs": cat_info["verbs"],
            "tenses": cat_info["tenses"]
        }

        # Process each verb in the category
        for verb in cat_info["verbs"]:
            if verb in output_data["verbs"]:
                continue  # Already processed

            verb_info = parser.get_verb_info(verb)
            if not verb_info:
                print(f"Warning: Could not find conjugations for '{verb}'")
                continue

            # Extract only the tenses we need
            conjugations = {}
            for simple_tense, (mood, xml_tense) in TENSE_MAPPING.items():
                if mood in verb_info['conjugations'] and xml_tense in verb_info['conjugations'][mood]:
                    conjugations[simple_tense] = verb_info['conjugations'][mood][xml_tense]
                else:
                    print(f"Warning: {verb} missing {simple_tense} ({mood}/{xml_tense})")

            output_data["verbs"][verb] = {
                "english": english_lookup.get(verb, ""),
                "conjugations": conjugations
            }

    # Save to JSON file
    output_file = os.path.join(cog_dir, 'verb_data.json')
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Successfully extracted data for {len(output_data['verbs'])} verbs")
    print(f"📁 Saved to: {output_file}")
    print(f"\nCategories:")
    for cat_id, cat_data in output_data["categories"].items():
        print(f"  - {cat_data['name']}: {len(cat_data['verbs'])} verbs")

if __name__ == "__main__":
    extract_verb_data()
