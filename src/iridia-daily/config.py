"""Configuration constants and mappings for Iridia Daily."""

CATEGORY_MAPPING = {
    'neuroscience': ('#9D4EDD', '🧠 NEUROSCIENCE', ['brain', 'memory', 'neuron', 'cognitive', 'mental']),
    'space': ('#4361EE', '🌌 SPACE', ['space', 'planet', 'star', 'galaxy', 'universe', 'cosmic']),
    'biology': ('#06D6A0', '🧬 BIOLOGY', ['cell', 'gene', 'dna', 'protein', 'biology', 'organism']),
    'environment': ('#26A69A', '🌍 ENVIRONMENT', ['climate', 'environment', 'earth', 'ocean', 'ecosystem']),
    'physics': ('#EF476F', '⚛️ PHYSICS', ['quantum', 'physics', 'particle', 'energy', 'atom']),
    'medicine': ('#F72585', '💊 MEDICINE', ['medicine', 'drug', 'treatment', 'disease', 'health']),
    'technology': ('#4CC9F0', '🤖 TECHNOLOGY', ['ai', 'algorithm', 'computer', 'data', 'software']),
    'default': ('#FF6B35', '🔬 RESEARCH', [])
}

SUBJECT_TEMPLATES = [
    "🌊 Your {day} Iridia Daily",  
    "🌊 Iridia Daily — {count} Research Insights Today",  
    "✨ Iridia Daily: {date}",  
    "🧪 Today's Iridia Daily"
]

PUBMED_SEARCH_TERMS = "(biology[MeSH] OR physics OR neuroscience OR astronomy OR chemistry OR psychology)"
PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"