from io import StringIO
from urllib.parse import urlparse

def remove_markdown_from_message(message: str) -> str:
    """
    Parses text and removes all markdown from it.
    Covers only Discord's subset of markdown.
    """

    # We need to handle bold/italics/underline/strikethrough (**, */_, __, ~~)
    # We need to handle hyperlinks ([hello](https://google.com/))
    # We need to handle code blocks (`hello`, ```hello```)
    # We need to handle spoilers (||hello||)
    # We need to handle quotes (> hello)
    # We need to handle escaped characters

    templates = ("||", "**", "*", "__", "_", "~~", "```", "`")
    supported_protocols = ("http", "https")

    index = 0
    output = StringIO()
    is_new_line = True
    expecting_closing = {}

    for template in templates:
        expecting_closing[template] = False

    while index < len(message):
        character = message[index]
        next_two = message[index:index+2]
        next_three = message[index:index+3]
        is_in_code_block = expecting_closing["`"] or expecting_closing["```"]

        # Handle escaped characters first
        if character == "\\" and not message[index + 1].isalnum() and not is_in_code_block:
            output.write(message[index + 1])
            index += 2
            is_new_line = False
            continue

        # Strip headers, subtext, and quotes
        if is_new_line and not is_in_code_block:
            if next_two == "> " or next_two == "# ":
                index += 2
                is_new_line = False
                continue

            if next_three == "## " or next_three == "-# ":
                index += 3
                is_new_line = False
                continue

            if message[index:index+4] == "### ":
                index += 4
                is_new_line = False
                continue

        should_continue_after_templates = False

        # Strip spoilers, bold, italics, underline, strikethrough, and code blocks
        for template in templates:
            if (expecting_closing["`"] and template != "`") or (expecting_closing["```"] and template != "```"):
                continue

            length = len(template)
            want_to_close = expecting_closing[template]

            if message[index:index+length] == template and (want_to_close or template in message[index+length:]):
                index += length

                if template == "```" and not want_to_close:
                    end = message.index(template, index + length)
                    
                    if "\n" in message[index + length:end]:
                        while message[index].isalnum():
                            index += 1

                expecting_closing[template] = not want_to_close
                should_continue_after_templates = True
                is_new_line = False
                break

        if should_continue_after_templates:
            continue

        # Strip hyperlinks
        if character == "[" and not is_in_code_block:
            new_index = index + 1
            label = StringIO()

            while new_index < len(message) and message[new_index] != "]":
                label.write(message[new_index])
                new_index += 1

            bounds_check = new_index >= len(message)
            if bounds_check or message[new_index + 1] != "(":
                output.write("[" + remove_markdown_from_message(label.getvalue()))

                if not bounds_check:
                    output.write("]")

                index = new_index + 2
                is_new_line = False
                continue

            # By this point, we know that `message[new_index]` is `]` and
            # that `message[new_index + 1]` is `(`, so we can skip 2 chars
            new_index += 2
            url = StringIO()

            while new_index < len(message) and message[new_index] != ")":
                url.write(message[new_index])
                new_index += 1

            bounds_check = new_index >= len(message)
            full_url = url.getvalue()
            if bounds_check or urlparse(full_url).scheme not in supported_protocols:
                output.write("[" + remove_markdown_from_message(label.getvalue()) + "](" + remove_markdown_from_message(full_url))

                if not bounds_check:
                    output.write(")")

                index = new_index + 1
                is_new_line = False
                continue

            output.write(remove_markdown_from_message(label.getvalue()))
            index = new_index + 1
            is_new_line = False
            continue

        # These should be normal characters which we can consume w/o concern
        is_new_line = character == "\n"
        output.write(character)
        index += 1

    return output.getvalue()