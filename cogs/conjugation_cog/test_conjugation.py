#!/usr/bin/env python3
"""
Simple test script for the conjugation cog
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from conjugation_data import get_random_verb, get_all_verbs, get_verbs_by_difficulty

def test_data_loading():
    """Test if the verb data loads correctly"""
    print("=== Testing Data Loading ===")
    
    # Test getting all verbs
    all_verbs = get_all_verbs()
    print(f"Total verbs loaded: {len(all_verbs)}")
    
    # Test getting a random verb
    random_verb = get_random_verb()
    print(f"Random verb: {random_verb['infinitive']} (difficulty: {random_verb.get('difficulty', 'unknown')})")
    
    # Test filtering by difficulty
    beginner_verbs = get_verbs_by_difficulty("beginner")
    intermediate_verbs = get_verbs_by_difficulty("intermediate")
    advanced_verbs = get_verbs_by_difficulty("advanced")
    
    print(f"Beginner verbs: {len(beginner_verbs)}")
    print(f"Intermediate verbs: {len(intermediate_verbs)}")
    print(f"Advanced verbs: {len(advanced_verbs)}")
    
    return all_verbs

def test_conjugation_logic():
    """Test basic conjugation logic without Discord dependencies"""
    print("\n=== Testing Conjugation Logic ===")
    
    verb_data = get_random_verb()
    tense = "presente"
    
    if tense in verb_data["conjugations"]:
        pronouns = list(verb_data["conjugations"][tense].keys())
        
        print(f"Testing verb: {verb_data['infinitive']}")
        print(f"Available pronouns: {pronouns}")
        
        for pronoun in pronouns:
            correct_answer = verb_data["conjugations"][tense][pronoun]
            print(f"  {pronoun}: {correct_answer}")
    else:
        print(f"Tense '{tense}' not found for verb '{verb_data['infinitive']}'")

def main():
    """Main test function"""
    print("Testing Conjugation Cog Components\n")
    
    try:
        # Test data loading
        verbs = test_data_loading()
        
        if verbs:
            # Test conjugation logic
            test_conjugation_logic()
            
            print("\n=== Sample Verbs ===")
            for i, verb in enumerate(verbs[:5]):  # Show first 5 verbs
                print(f"{i+1}. {verb['infinitive']} ({verb.get('difficulty', 'unknown')})")
                if 'presente' in verb['conjugations']:
                    presente = verb['conjugations']['presente']
                    print(f"   yo: {presente.get('yo', '?')}")
                    print(f"   tú: {presente.get('tú', '?')}")
                    print(f"   él/ella: {presente.get('él/ella', '?')}")
                print()
        
        print("✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
