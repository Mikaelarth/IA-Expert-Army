import re
import unicodedata


def slugify(text: str) -> str:
    # Normalize the text to decompose accents and diacritiques
    normalized_text = unicodedata.normalize('NFD', text)
    # Remove non-ASCII characters
    ascii_text = ''.join(char for char in normalized_text if unicodedata.category(char) != 'Mn')
    # Convert to lowercase
    lowercased_text = ascii_text.lower()
    # Replace non-alphanumeric characters with '-'
    hyphenated_text = re.sub(r'[^a-z0-9]+', '-', lowercased_text)
    # Remove leading and trailing hyphens
    slug = hyphenated_text.strip('-')
    return slug
