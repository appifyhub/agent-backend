import re


def escape_markdown(text: str) -> str:
    """
    Escape special characters for Telegram legacy markdown mode.
    Required characters: _ * ` [

    Telegram's markdown format (different from standard markdown!):
    - *bold* (single asterisk, not double!)
    - _italic_ (underscore)
    - `code` (backtick)

    Strategy:
    1. Always escape backslashes first (escape character itself)
    2. Protect Telegram markdown patterns (*bold*, _italic_, `code`), then escape remaining chars
    3. For [: always escape (rarely used intentionally in our context)

    This preserves intentional formatting like *bold*, _italic_, `code` while
    escaping problematic characters like snake_case, 2*3*4, etc.
    """
    if not text:
        return text

    # Always escape backslashes first (they're the escape character)
    text = text.replace("\\", "\\\\")

    # Strategy: Protect markdown patterns first, then escape unprotected special chars
    # Using null bytes as placeholders (won't appear in normal text)
    BOLD_START = "\x00BS\x00"
    BOLD_END = "\x00BE\x00"
    ITALIC_START = "\x00IS\x00"
    ITALIC_END = "\x00IE\x00"
    CODE_START = "\x00CS\x00"
    CODE_END = "\x00CE\x00"
    CODE_CONTENT = "\x00CC{}\x00"

    # Protect code blocks and inline code (including their content)
    # We need to protect the content from escaping
    # IMPORTANT: Handle triple backticks FIRST (code blocks), then single backticks (inline code)
    code_blocks = []  # Stores tuples of (content, delimiter) where delimiter is ``` or `

    def protect_code_block(match):
        content = match.group(1)
        idx = len(code_blocks)
        code_blocks.append((content, "```"))
        return f"{CODE_START}{CODE_CONTENT.format(idx)}{CODE_END}"

    def protect_inline_code(match):
        content = match.group(1)
        idx = len(code_blocks)
        code_blocks.append((content, "`"))
        return f"{CODE_START}{CODE_CONTENT.format(idx)}{CODE_END}"

    # First protect ```code blocks``` (triple backticks, can span multiple lines)
    text = re.sub(r"```(.+?)```", protect_code_block, text, flags = re.DOTALL)
    # Then protect `inline code` (single backticks, must not span lines)
    text = re.sub(r"`([^`\n]+?)`", protect_inline_code, text)

    # Protect **bold** (double asterisk - standard markdown, also works in Telegram)
    # Must match double asterisks first before single asterisks
    text = re.sub(r"\*\*([^*]+?)\*\*", rf"{BOLD_START}{BOLD_START}\1{BOLD_END}{BOLD_END}", text)

    # Protect *bold* (single asterisk - Telegram's format, not standard markdown!)
    # Uses negative lookbehind/lookahead for word chars to allow punctuation adjacency:
    # *bold*, and *bold*. are preserved, while 2*3*4 (word-char adjacent) still gets escaped
    text = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", rf"{BOLD_START}\1{BOLD_END}", text)

    # Protect _italic_ (underscore italic - allow spaces inside)
    text = re.sub(r"\b_([^_]+?)_\b", rf"{ITALIC_START}\1{ITALIC_END}", text)

    # Now escape all remaining special characters
    text = text.replace("*", "\\*")
    text = text.replace("_", "\\_")
    text = text.replace("`", "\\`")
    text = text.replace("[", "\\[")

    # Restore protected patterns
    text = text.replace(BOLD_START, "*")
    text = text.replace(BOLD_END, "*")
    text = text.replace(ITALIC_START, "_")
    text = text.replace(ITALIC_END, "_")

    # Restore code blocks and inline code with correct delimiters
    for idx, (content, delimiter) in enumerate(code_blocks):
        placeholder = f"{CODE_START}{CODE_CONTENT.format(idx)}{CODE_END}"
        text = text.replace(placeholder, f"{delimiter}{content}{delimiter}")

    return text


def calculate_rendered_length(text: str) -> int:
    parsed_text = escape_markdown(text)
    length = 0
    index = 0
    while index < len(parsed_text):
        character = parsed_text[index]
        if (
            character == "\\"
            and index + 1 < len(parsed_text)
            and parsed_text[index + 1] in "_*`["
        ):
            length += 1
            index += 2
            continue
        if character not in "_*`[":
            length += 1
            index += 1
            continue

        closing_character = "]" if character == "[" else character
        content_start = index + 1
        closing_marker = closing_character
        if parsed_text.startswith("```", index):
            content_start = index + 3
            language_end = content_start
            while (
                language_end < len(parsed_text)
                and not parsed_text[language_end].isspace()
                and parsed_text[language_end] != "`"
            ):
                language_end += 1
            if (
                language_end > content_start
                and language_end < len(parsed_text)
                and parsed_text[language_end] != "`"
            ):
                content_start = language_end
            if parsed_text[content_start:content_start + 2] in ("\n\r", "\r\n"):
                content_start += 2
            elif content_start < len(parsed_text) and parsed_text[content_start] in "\n\r":
                content_start += 1
            closing_marker = "```"

        content_end = parsed_text.find(closing_marker, content_start)
        if content_end < 0:
            length += 1
            index += 1
            continue
        length += len(parsed_text[content_start:content_end])
        index = content_end + len(closing_marker)
        if character == "[" and index < len(parsed_text) and parsed_text[index] == "(":
            closing_parenthesis = parsed_text.find(")", index + 1)
            index = len(parsed_text) if closing_parenthesis < 0 else closing_parenthesis + 1
    return length
