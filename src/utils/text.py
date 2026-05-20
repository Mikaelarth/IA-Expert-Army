import re
import unicodedata

def slugify(text: str) -> str:
    # Convert to lowercase
    text = text.lower()
    
    # Normalize and remove diacritics
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(char for char in text if not unicodedata.combining(char))
    
    # Replace non-alphanumeric characters with '-'
    text = re.sub(r'[^a-z0-9]', '-', text)
    
    # Compress consecutive '-' into a single '-'
    text = re.sub(r'-+', '-', text)
    
    # Strip leading and trailing '-'
    return text.strip('-')
