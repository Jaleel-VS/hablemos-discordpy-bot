"""
XML Parser for Spanish verb conjugations
Converts the XML data into Python dictionaries for use in the Discord bot
"""

import xml.etree.ElementTree as ET
import json
from typing import Dict, List, Optional

def _first_i_text(person_element: ET.Element) -> str:
    """Return only the first <i> child text for a <p> element.

    The dataset may include multiple <i> tags per person to denote
    alternatives. For MVP, we deliberately take only the first entry
    and do not concatenate multiple segments.
    """
    first = person_element.find('i')
    return (first.text or '').strip() if first is not None else ''

class SpanishVerbParser:
    def __init__(self, verbs_xml_path: str, conjugations_xml_path: str):
        self.verbs_xml_path = verbs_xml_path
        self.conjugations_xml_path = conjugations_xml_path
        self.conjugation_templates = {}
        self.verbs = {}
        
        # Spanish pronouns in order (6 persons for most moods)
        self.pronouns = ["yo", "tú", "él/ella", "nosotros", "vosotros", "ellos/ellas"]
        # Imperative pronouns (5 persons, no "yo")
        self.imperative_pronouns = ["tú", "él/ella/usted", "nosotros", "vosotros", "ellos/ellas/ustedes"]
        
    def parse_conjugation_templates(self):
        """Parse the conjugation templates XML file"""
        print("Parsing conjugation templates...")
        tree = ET.parse(self.conjugations_xml_path)
        root = tree.getroot()
        
        for template in root.findall('template'):
            template_name = template.get('name')
            template_data = {}
            
            # Parse Indicativo (Indicative mood)
            indicativo = template.find('Indicativo')
            if indicativo is not None:
                template_data['indicativo'] = {}
                
                # Present tense
                presente = indicativo.find('presente')
                if presente is not None:
                    endings = [_first_i_text(p) for p in presente.findall('p')]
                    template_data['indicativo']['presente'] = endings
                
                # Preterite imperfect
                preterito_imperfecto = indicativo.find('pretérito-imperfecto')
                if preterito_imperfecto is not None:
                    endings = [_first_i_text(p) for p in preterito_imperfecto.findall('p')]
                    template_data['indicativo']['pretérito-imperfecto'] = endings
                    
                # Preterite perfect simple (preterite)
                preterito_perfecto = indicativo.find('pretérito-perfecto-simple')
                if preterito_perfecto is not None:
                    endings = [_first_i_text(p) for p in preterito_perfecto.findall('p')]
                    template_data['indicativo']['pretérito-perfecto-simple'] = endings
                    
                # Future
                futuro = indicativo.find('futuro')
                if futuro is not None:
                    endings = [_first_i_text(p) for p in futuro.findall('p')]
                    template_data['indicativo']['futuro'] = endings
            
            # Parse Subjuntivo (Subjunctive mood) - all tenses
            subjuntivo = template.find('Subjuntivo')
            if subjuntivo is not None:
                template_data['subjuntivo'] = {}
                
                for tense_elem in subjuntivo:
                    tense_name = tense_elem.tag
                    endings = [_first_i_text(p) for p in tense_elem.findall('p')]
                    template_data['subjuntivo'][tense_name] = endings
            
            # Parse Condicional (Conditional mood)
            condicional = template.find('Condicional')
            if condicional is not None:
                template_data['condicional'] = {}
                
                for tense_elem in condicional:
                    tense_name = tense_elem.tag
                    endings = [_first_i_text(p) for p in tense_elem.findall('p')]
                    template_data['condicional'][tense_name] = endings
            
            # Parse Imperativo (Imperative mood)
            imperativo = template.find('Imperativo')
            if imperativo is not None:
                template_data['imperativo'] = {}
                
                for tense_elem in imperativo:
                    tense_name = tense_elem.tag
                    # Imperative has 5 persons, not 6 (no "yo" form)
                    endings = [_first_i_text(p) for p in tense_elem.findall('p')]
                    template_data['imperativo'][tense_name] = endings
            
            self.conjugation_templates[template_name] = template_data
            
        print(f"Loaded {len(self.conjugation_templates)} conjugation templates")
    
    def parse_verbs(self):
        """Parse the verbs XML file"""
        print("Parsing verbs...")
        tree = ET.parse(self.verbs_xml_path)
        root = tree.getroot()
        
        for verb in root.findall('v'):
            infinitive_elem = verb.find('i')
            template_elem = verb.find('t')
            
            if infinitive_elem is not None and template_elem is not None:
                infinitive = infinitive_elem.text or ""
                template = template_elem.text or ""
                
                self.verbs[infinitive] = {
                    'infinitive': infinitive,
                    'template': template
                }
            
        print(f"Loaded {len(self.verbs)} verbs")
    
    def conjugate_verb(self, infinitive: str, template_name: str, tense: str = 'presente', mood: str = 'indicativo') -> Optional[Dict]:
        """Conjugate a verb using its template"""
        if template_name not in self.conjugation_templates:
            return None
            
        template = self.conjugation_templates[template_name]
        
        if mood not in template or tense not in template[mood]:
            return None
            
        endings = template[mood][tense]
        
        # Extract radical from template name and infinitive
        if ':' in template_name:
            radical_pattern, ending_pattern = template_name.split(':', 1)
            
            # Special case for irregular verbs with empty radical pattern (like ":ser")
            if not radical_pattern:
                # For verbs like "ser" with template ":ser", use the endings as complete forms
                radical = ""
            else:
                # Calculate the actual radical by removing the ending pattern from the infinitive
                if infinitive.endswith(ending_pattern):
                    radical = infinitive[:-len(ending_pattern)]
                else:
                    # Fallback: use the template's radical pattern
                    radical = radical_pattern
        else:
            # Template without colon (shouldn't happen in this dataset)
            radical = infinitive[:-2]
            
        # Create conjugated forms
        conjugated = {}
        
        # Use appropriate pronoun set based on mood
        if mood == 'imperativo':
            pronoun_set = self.imperative_pronouns
        else:
            pronoun_set = self.pronouns
            
        for i, pronoun in enumerate(pronoun_set):
            if i < len(endings):
                conjugated[pronoun] = radical + endings[i]
            
        return conjugated
    
    def get_common_verbs(self, limit: int = 200, include_all_tenses: bool = True) -> List[Dict]:
        """Get a list of common Spanish verbs with their conjugations"""
        # Load the 200 most common verbs from frequency data
        common_verbs = self._load_200_common_verbs()
        
        result = []
        for verb_info in common_verbs[:limit]:
            verb = verb_info['infinitive']
            if verb in self.verbs:
                verb_data = self.verbs[verb]
                template_name = verb_data['template']
                
                # Get all available conjugations for this verb
                conjugations = {}
                if include_all_tenses:
                    verb_conjugations = self.get_verb_info(verb)
                    if verb_conjugations:
                        conjugations = verb_conjugations['conjugations']
                else:
                    # Just get present tense (backward compatibility)
                    present_conj = self.conjugate_verb(verb, template_name, 'presente', 'indicativo')
                    if present_conj:
                        conjugations = {'indicativo': {'presente': present_conj}}
                
                if conjugations:
                    result.append({
                        'infinitive': verb,
                        'template': template_name,
                        'english': verb_info.get('english', ''),
                        'frequency_rank': verb_info.get('frequency_rank', 999),
                        'conjugations': conjugations,
                        'difficulty': self._get_difficulty(verb, template_name, verb_info.get('frequency_rank', 999))
                    })
                    
        return result
    
    def _load_200_common_verbs(self) -> List[Dict]:
        """Load the 200 most common Spanish verbs from JSON file"""
        import os
        json_path = os.path.join(os.path.dirname(__file__), 'data', '200_common_verbs.json')
        
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"Warning: {json_path} not found. Using fallback list.")
            # Fallback to a minimal set if file missing
            return [
                {'infinitive': 'ser', 'english': 'to be', 'frequency_rank': 1},
                {'infinitive': 'estar', 'english': 'to be', 'frequency_rank': 2},
                {'infinitive': 'tener', 'english': 'to have', 'frequency_rank': 3},
                {'infinitive': 'hacer', 'english': 'to make/do', 'frequency_rank': 4},
                {'infinitive': 'hablar', 'english': 'to speak', 'frequency_rank': 5}
            ]
    
    def _get_difficulty(self, verb: str, template: str, frequency_rank: int = 999) -> str:
        """Determine difficulty level based on verb frequency, template, and irregularity"""
        # Most common verbs (top 20) are beginner-friendly regardless of irregularity
        if frequency_rank <= 20:
            return 'beginner'
        
        # Regular verbs are easier
        if template in ['cort:ar', 'deb:er', 'viv:ir']:
            return 'beginner' if frequency_rank <= 100 else 'intermediate'
        
        # Highly irregular verbs (empty radical) are harder
        if template.startswith(':'):
            return 'intermediate' if frequency_rank <= 50 else 'advanced'
            
        # Stem-changing and other irregular patterns
        return 'intermediate' if frequency_rank <= 100 else 'advanced'
    

    
    def get_verb_info(self, infinitive: str) -> Optional[Dict]:
        """Get detailed information about a specific verb"""
        if infinitive not in self.verbs:
            return None
            
        verb_data = self.verbs[infinitive]
        template_name = verb_data['template']
        
        result = {
            'infinitive': infinitive,
            'template': template_name,
            'conjugations': {},
            'difficulty': self._get_difficulty(infinitive, template_name)
        }
        
        # Get all available tenses
        if template_name in self.conjugation_templates:
            template = self.conjugation_templates[template_name]
            
            for mood in template:
                result['conjugations'][mood] = {}
                for tense in template[mood]:
                    conjugated = self.conjugate_verb(infinitive, template_name, tense, mood)
                    if conjugated:
                        result['conjugations'][mood][tense] = conjugated
        
        return result

def main():
    """Main function to demonstrate usage"""
    parser = SpanishVerbParser(
        'data/verbs-es.xml',
        'data/conjugations-es.xml'
    )
    
    # Parse the XML files
    parser.parse_conjugation_templates()
    parser.parse_verbs()
    
    # Show statistics about loaded data
    common_verbs = parser.get_common_verbs(200)
    print(f"Loaded {len(common_verbs)} common verbs from 200 most frequent")
    
    # Test specific verbs
    test_verbs = ['hablar', 'ser', 'tener', 'hacer']
    for verb in test_verbs:
        print(f"\n--- {verb.upper()} ---")
        verb_info = parser.get_verb_info(verb)
        if verb_info:
            if 'indicativo' in verb_info['conjugations'] and 'presente' in verb_info['conjugations']['indicativo']:
                present = verb_info['conjugations']['indicativo']['presente']
                for pronoun, conjugation in present.items():
                    print(f"{pronoun}: {conjugation}")
        else:
            print(f"Verb '{verb}' not found")

if __name__ == "__main__":
    main()
