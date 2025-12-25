"""
Configuration data for language learning conversations
Includes categories, levels, languages, and scenario definitions
"""

# Categories with emojis and scenario ideas for each level
CATEGORIES = {
    'restaurant': {
        'name': 'Restaurant',
        'emoji': '🍽️',
        'scenarios': {
            'beginner': [
                'ordering a simple meal at a restaurant',
                'asking for the check after dinner',
                'requesting water or condiments',
                'making a simple food choice from a menu',
                'asking about prices at a café',
            ],
            'intermediate': [
                'making a reservation for dinner',
                'asking about ingredients and preparation',
                'handling a food allergy or dietary restriction',
                'requesting a table change or special seating',
                'discussing menu recommendations with waiter',
            ],
            'advanced': [
                'discussing wine pairings with a sommelier',
                'complaining diplomatically about service issues',
                'negotiating a group dinner menu and pricing',
                'discussing local cuisine and cooking techniques',
                'handling a billing error or split payment',
            ]
        }
    },
    'travel': {
        'name': 'Travel',
        'emoji': '✈️',
        'scenarios': {
            'beginner': [
                'checking into a hotel',
                'asking for directions to a landmark',
                'buying a bus or train ticket',
                'asking about opening hours at a tourist site',
                'requesting help with luggage',
            ],
            'intermediate': [
                'dealing with lost luggage at airport',
                'changing a flight or hotel booking',
                'asking about local attractions and tours',
                'renting a car and understanding insurance',
                'discussing transportation options with concierge',
            ],
            'advanced': [
                'negotiating with a travel agent for better rates',
                'explaining a complex visa or immigration situation',
                'discussing travel insurance claims after incident',
                'arranging special accommodations for group travel',
                'mediating a dispute over travel booking error',
            ]
        }
    },
    'shopping': {
        'name': 'Shopping',
        'emoji': '🛍️',
        'scenarios': {
            'beginner': [
                'buying clothes and asking for sizes',
                'paying at a cashier',
                'asking for prices of items',
                'finding a specific product in a store',
                'asking if a store accepts credit cards',
            ],
            'intermediate': [
                'returning or exchanging purchased items',
                'asking about sales, discounts, and promotions',
                'comparing different products and features',
                'negotiating a better price at a market',
                'asking about warranty or guarantee policies',
            ],
            'advanced': [
                'negotiating bulk purchase pricing for business',
                'discussing product quality and manufacturing details',
                'handling a complex billing dispute or refund',
                'comparing import options and shipping logistics',
                'discussing sustainable or ethical sourcing practices',
            ]
        }
    },
    'workplace': {
        'name': 'Workplace',
        'emoji': '💼',
        'scenarios': {
            'beginner': [
                'introducing yourself to new colleagues',
                'asking about break times and lunch hours',
                'requesting basic office supplies',
                'asking where to find something in office',
                'greeting coworkers in the morning',
            ],
            'intermediate': [
                'scheduling a meeting with colleagues',
                'giving a status update on a project',
                'requesting time off or vacation days',
                'discussing task priorities with supervisor',
                'collaborating on a team assignment',
            ],
            'advanced': [
                'conducting a performance review discussion',
                'negotiating responsibilities for team project',
                'mediating a conflict between team members',
                'proposing and defending a new business initiative',
                'discussing sensitive HR or workplace issues',
            ]
        }
    },
    'social': {
        'name': 'Social/Casual',
        'emoji': '👥',
        'scenarios': {
            'beginner': [
                'greeting someone and making small talk',
                'talking about hobbies and interests',
                'making plans for the weekend',
                'talking about the weather',
                'introducing family members',
            ],
            'intermediate': [
                'discussing current events or recent news',
                'sharing opinions about movies or music',
                'talking about family and relationships',
                'discussing travel experiences',
                'making and accepting social invitations',
            ],
            'advanced': [
                'debating a controversial topic respectfully',
                'discussing philosophical or abstract concepts',
                'navigating a sensitive personal conversation',
                'giving advice on a complex life situation',
                'discussing cultural differences and perspectives',
            ]
        }
    }
}

# Difficulty levels with learning guidance
LEVELS = {
    'beginner': {
        'name': 'Beginner',
        'emoji': '🟢',
        'description': 'A1-A2 level (CEFR)',
        'vocabulary_guidance': 'Use simple, common vocabulary that beginners would know. Focus on everyday words. Present tense primarily. Keep sentences short (5-10 words).',
        'grammar_guidance': 'Basic sentence structures only. Use present tense mostly. Avoid subjunctive mood or complex tenses. Simple questions and statements.',
        'exchange_count': (6, 8),
        'temperature': 0.7
    },
    'intermediate': {
        'name': 'Intermediate',
        'emoji': '🟡',
        'description': 'B1-B2 level (CEFR)',
        'vocabulary_guidance': 'Moderate vocabulary with some idiomatic expressions. Mix of common and semi-advanced words. Use various tenses (past, present, future).',
        'grammar_guidance': 'Use past, present, and future tenses. Include some conditional phrases. Can use more complex sentence structures.',
        'exchange_count': (6, 8),
        'temperature': 0.8
    },
    'advanced': {
        'name': 'Advanced',
        'emoji': '🔴',
        'description': 'C1-C2 level (CEFR)',
        'vocabulary_guidance': 'Rich, nuanced vocabulary with idioms, colloquialisms, and specialized terms. Natural flow with cultural references.',
        'grammar_guidance': 'Full range of tenses including subjunctive mood. Complex sentence structures with subordinate clauses. Natural, sophisticated language.',
        'exchange_count': (6, 8),
        'temperature': 0.9
    }
}

# Supported languages
LANGUAGES = {
    'spanish': {
        'name': 'Spanish',
        'emoji': '🇪🇸',
        'code': 'es',
        'full_name': 'Español'
    },
    'english': {
        'name': 'English',
        'emoji': '🇬🇧',
        'code': 'en',
        'full_name': 'English'
    }
}

# Aliases for flexible command input
LANGUAGE_ALIASES = {
    'spanish': 'spanish',
    'spa': 'spanish',
    'es': 'spanish',
    'español': 'spanish',
    'english': 'english',
    'eng': 'english',
    'en': 'english'
}

LEVEL_ALIASES = {
    'beginner': 'beginner',
    'beg': 'beginner',
    'a1': 'beginner',
    'a2': 'beginner',
    'intermediate': 'intermediate',
    'int': 'intermediate',
    'b1': 'intermediate',
    'b2': 'intermediate',
    'advanced': 'advanced',
    'adv': 'advanced',
    'c1': 'advanced',
    'c2': 'advanced'
}

CATEGORY_ALIASES = {
    'restaurant': 'restaurant',
    'rest': 'restaurant',
    'food': 'restaurant',
    'dining': 'restaurant',
    'travel': 'travel',
    'trip': 'travel',
    'vacation': 'travel',
    'shopping': 'shopping',
    'shop': 'shopping',
    'store': 'shopping',
    'workplace': 'workplace',
    'work': 'workplace',
    'office': 'workplace',
    'job': 'workplace',
    'social': 'social',
    'casual': 'social',
    'friends': 'social',
    'chat': 'social'
}
