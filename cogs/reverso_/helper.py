class HelperFunctions:
    language_codes = {}

    def __init__(self) -> None:
        self.language_codes = codes = {'en': "English",
                                       'ar': "Arabic",
                                       'es': "Spanish",
                                       'de': "German",
                                       'fr': "French",
                                       'he': "Hebrew",
                                       'it': "Italian",
                                       'ja': "Japanese",
                                       'nl': "Dutch",
                                       'pl': "Polish",
                                       'pt': "Portuguese",
                                       'ro': "Romanian",
                                       'ru': "Russian"}

    @staticmethod
    def highlight_example(text, highlighted):
        """'Highlights' ALL the highlighted parts of the word usage example with * characters.
        Args:
            text: The text of the example
            highlighted: Indexes of the highlighted parts' indexes
        Returns:
            The highlighted word usage example
        """

        def insert_char(string, index, char):
            """Inserts the given character into a string.
            Example:
                string = "abc"
                index = 1
                char = "+"
                Returns: "a+bc"
            Args:
                string: Given string
                index: Index where to insert
                char: Which char to insert
            Return:
                String string with character char inserted at index index.
            """

            return string[:index] + char + string[index:]

        def highlight_once(string, start, end, shift):
            """'Highlights' ONE highlighted part of the word usage example with two pairs of ** characters.
            Example:
                string = "This is a sample string"
                start = 0
                end = 4
                shift = 0
                Returns: "*This* is a sample string"
            Args:
                string: The string to be highlighted
                start: The start index of the highlighted part
                end: The end index of the highlighted part
                shift: How many highlighting chars were already inserted (to get right indexes)
            Returns:
                The highlighted string.
            """

            s = insert_char(string, start + shift, "*")
            s = insert_char(s, end + shift + 1, "*")
            return s

        shift = 0
        for start, end in highlighted:
            text = highlight_once(text, start, end, shift)
            shift += 2

        return text.replace("*", "**")
