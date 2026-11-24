"""Hide personal data before any text reaches an AI model (AI2).

Names, email addresses, phone numbers and postal addresses are replaced with
the tags [NAME], [EMAIL], [PHONE] and [ADDRESS].

The rules are deliberately simple and predictable (regular expressions, no
machine-learning model), so they are fast, free and fully unit-tested. They
lean towards hiding too much rather than too little. Known limit: a name with
no clue around it ("my name is", "Mr", "my manager") is only caught if it was
already found elsewhere in the same text.
"""

import re

NAME = "[NAME]"
EMAIL = "[EMAIL]"
PHONE = "[PHONE]"
ADDRESS = "[ADDRESS]"

# Emails, written ("sam.lee@gmail.com") or spoken ("sam dot lee at gmail dot com").
WRITTEN_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
SPOKEN_EMAIL = re.compile(
    r"\b\w+(?:\s+dot\s+\w+)*\s+at\s+\w+(?:\s+dot\s+\w+)*"
    r"\s+dot\s+(?:com|co|uk|org|net|io|ac|gov|edu|info|biz|me)\b",
    re.IGNORECASE,
)

# Phone numbers: a run of digits, spaces, dashes, dots and brackets, optionally
# starting with +. Only runs with 9 to 15 digits count, so years, prices and
# quantities are left alone.
PHONE_CANDIDATE = re.compile(r"(?<![\w+])\+?\(?\d[\d\s().-]{6,}\d(?!\w)")

# UK postcodes, e.g. "SW1A 1AA", "M1 1AE", "g2 3ab".
POSTCODE = re.compile(r"\b[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}\b", re.IGNORECASE)

# Street addresses, e.g. "221B Baker Street", "12 Station Road".
STREET_ADDRESS = re.compile(
    r"\b\d{1,4}[A-Za-z]?,?\s+(?:[A-Z][\w'-]*\s+){1,3}"
    r"(?i:street|st|road|rd|avenue|ave|lane|ln|drive|close|way|place|court|crescent"
    r"|terrace|gardens|square|grove|hill|park|row|mews|walk)\b\.?"
)

# A name is one to three capitalised words, e.g. "Sam", "Mary-Jane O'Neill".
NAME_WORD = r"(?:[A-Z][a-z]*(?:['’][A-Z][a-z]+)|[A-Z][a-z]+(?:-[A-Z][a-z]+)*)"
NAME_WORDS = rf"{NAME_WORD}(?:\s+{NAME_WORD}){{0,2}}"

# Clues that the next words are someone's name.
NAME_AFTER_CLUE = re.compile(
    r"(?:\b(?i:name\s+is|name's|i'm\s+called|i\s+am\s+called|call\s+me|named)"
    r"|\b(?i:my|our)\s+(?i:wife|husband|partner|colleague|manager|boss|friend|son"
    r"|daughter|brother|sister|mum|dad|mother|father|assistant|accountant|director"
    r"|business\s+partner)(?:\s+(?i:is\s+called|is\s+named|is|called|named))?)"
    rf"\s+(?P<name>{NAME_WORDS})"
)
NAME_AFTER_TITLE = re.compile(rf"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof)\.?\s+(?P<name>{NAME_WORDS})")


# Capitalised words that are never part of a name, so "call me Monday" or
# "Mr Smith Then" doesn't hide every "Monday" or "Then" in the text.
NOT_NAMES = {
    "I", "The", "A", "An", "And", "But", "Or", "So", "Then", "Also", "Yes", "No",
    "We", "Our", "My", "He", "She", "They", "It", "This", "That", "There",
    "In", "On", "At", "From", "For", "With", "To", "Of", "By", "If", "When",
    "Hi", "Hello", "Thanks", "Okay", "Ok", "Please",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
    "January", "February", "March", "April", "May", "June", "July", "August",
    "September", "October", "November", "December",
}


def _mask_phone(match: re.Match) -> str:
    digits = sum(character.isdigit() for character in match.group())
    return PHONE if 9 <= digits <= 15 else match.group()


def _find_names(text: str) -> set[str]:
    names: set[str] = set()
    for pattern in (NAME_AFTER_CLUE, NAME_AFTER_TITLE):
        for match in pattern.finditer(text):
            parts = []
            for word in match.group("name").split():
                if word in NOT_NAMES:
                    break
                parts.append(word)
            if parts:
                names.add(" ".join(parts))
                # Also hide each part, so a later "Sam" is caught after "Sam Lee".
                names.update(part for part in parts if len(part) > 1)
    return names


def mask_personal_data(text: str) -> str:
    """Return `text` with personal data replaced by tags."""
    # Order matters: emails contain names, and addresses contain numbers.
    text = WRITTEN_EMAIL.sub(EMAIL, text)
    text = SPOKEN_EMAIL.sub(EMAIL, text)
    text = STREET_ADDRESS.sub(ADDRESS, text)
    text = POSTCODE.sub(ADDRESS, text)
    text = PHONE_CANDIDATE.sub(_mask_phone, text)

    # Longest names first, so "Sam Lee" is replaced before "Sam".
    for name in sorted(_find_names(text), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(name)}\b", NAME, text)
    return text