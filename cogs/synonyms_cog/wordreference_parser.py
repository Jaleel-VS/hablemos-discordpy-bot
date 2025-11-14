"""
Parser for WordReference synonym/antonym pages
"""
import requests
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class WordReferenceParser:
    """Parser for extracting synonyms and antonyms from WordReference"""

    BASE_URL = "https://www.wordreference.com/sinonimos/{word}"
    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)

    def fetch_word(self, word: str, timeout: int = 10) -> Optional[Dict[str, any]]:
        """
        Fetch synonyms and antonyms for a given word

        Args:
            word: The Spanish word to look up
            timeout: Request timeout in seconds

        Returns:
            Dictionary with word, synonym_groups, and antonym_groups
            None if word not found or error occurs
        """
        url = self.BASE_URL.format(word=word.lower().strip())

        try:
            logger.info(f"Fetching synonyms for: {word}")
            response = self.session.get(url, timeout=timeout)
            response.raise_for_status()

            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')

            # Check if word was found
            no_entry = soup.find('p', {'id': 'noEntryFound'})
            if no_entry:
                logger.info(f"No entry found for: {word}")
                return None

            # Find the main content div
            content_div = soup.find('div', class_='trans')
            if not content_div:
                logger.warning(f"Could not find content div for: {word}")
                return None

            # Extract the word heading
            word_heading = content_div.find('h3')
            if not word_heading:
                logger.warning(f"Could not find word heading for: {word}")
                return None

            found_word = word_heading.get_text().strip()

            # Extract synonym groups and antonyms
            synonym_groups = []
            antonym_groups = []

            # Find all list items in the main ul
            main_ul = content_div.find('ul')
            if main_ul:
                # Get direct children li elements only
                for li in main_ul.find_all('li', recursive=False):
                    # Check if this li contains antonyms (nested ul with span.r)
                    nested_ul = li.find('ul')
                    if nested_ul:
                        # This is a synonym group that might have antonyms
                        # Get the synonym text (everything before the nested ul)
                        synonym_text = ''
                        for content in li.children:
                            if content.name == 'ul':
                                break
                            if hasattr(content, 'get_text'):
                                synonym_text += content.get_text()
                            elif isinstance(content, str):
                                synonym_text += content

                        if synonym_text.strip():
                            synonyms = [s.strip() for s in synonym_text.split(',') if s.strip()]
                            if synonyms:
                                synonym_groups.append(synonyms)

                        # Extract antonyms from nested ul
                        antonym_span = nested_ul.find('span', class_='r')
                        if antonym_span:
                            antonym_text = antonym_span.get_text()
                            if 'Antónimos:' in antonym_text:
                                antonym_text = antonym_text.replace('Antónimos:', '').strip()
                                antonyms = [a.strip() for a in antonym_text.split(',') if a.strip()]
                                if antonyms:
                                    antonym_groups.append(antonyms)
                    else:
                        # Regular synonym group without antonyms
                        synonym_text = li.get_text().strip()
                        if synonym_text and synonym_text != 'Antónimos:':
                            synonyms = [s.strip() for s in synonym_text.split(',') if s.strip()]
                            if synonyms:
                                synonym_groups.append(synonyms)

            # Also check for standalone antonym spans (sometimes they appear differently)
            all_antonym_spans = content_div.find_all('span', class_='r')
            for span in all_antonym_spans:
                text = span.get_text()
                if 'Antónimos:' in text:
                    antonym_text = text.replace('Antónimos:', '').strip()
                    antonyms = [a.strip() for a in antonym_text.split(',') if a.strip()]
                    if antonyms and antonyms not in antonym_groups:
                        antonym_groups.append(antonyms)

            result = {
                'word': found_word,
                'synonym_groups': synonym_groups,
                'antonym_groups': antonym_groups,
                'url': url
            }

            logger.info(f"Successfully parsed {found_word}: {len(synonym_groups)} synonym groups, {len(antonym_groups)} antonym groups")
            return result

        except requests.RequestException as e:
            logger.error(f"Request error fetching {word}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error parsing {word}: {e}", exc_info=True)
            return None

    def get_synonym_count(self, data: Dict) -> int:
        """Get total number of unique synonyms"""
        if not data or 'synonym_groups' not in data:
            return 0
        all_synonyms = set()
        for group in data['synonym_groups']:
            all_synonyms.update(group)
        return len(all_synonyms)

    def get_antonym_count(self, data: Dict) -> int:
        """Get total number of unique antonyms"""
        if not data or 'antonym_groups' not in data:
            return 0
        all_antonyms = set()
        for group in data['antonym_groups']:
            all_antonyms.update(group)
        return len(all_antonyms)
