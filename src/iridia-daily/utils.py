"""Utility functions."""

from .config import CATEGORY_MAPPING

def get_category_info(text):
    """Determine category color and label based on content."""
    text_lower = text.lower()
    for category, (color, label, keywords) in CATEGORY_MAPPING.items():
        if category != 'default' and any(word in text_lower for word in keywords):
            return color, label
    return CATEGORY_MAPPING['default'][:2]