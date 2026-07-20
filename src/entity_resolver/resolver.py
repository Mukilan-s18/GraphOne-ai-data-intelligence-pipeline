import logging
from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)

# Mock database of 50 known AI startups
SEED_STARTUPS = [
    "OpenAI", "Anthropic", "DeepMind", "Hugging Face", "Cohere", "Midjourney",
    "Stability AI", "Runway", "Scale AI", "Inflection AI", "Mistral AI",
    "Adept AI", "Character.ai", "Perplexity AI", "Jasper", "Synthesia",
    "Glean", "Harvey", "Typeface", "Descript", "Copy.ai", "Otter.ai",
    "Grammarly", "Notion", "Canva", "Tome", "Replit", "GitHub", "Pinecone",
    "Weaviate", "Milvus", "Qdrant", "Chroma", "LangChain", "LlamaIndex",
    "Weights & Biases", "Snorkel AI", "DataRobot", "Dataiku", "H2O.ai",
    "Databricks", "Snowflake", "Palantir", "Anduril", "Shield AI",
    "Wayve", "Cruise", "Waymo", "Tesla", "Nvidia"
]

def clean_entity_name(name: str) -> str:
    """Removes common corporate suffixes and normalizes case."""
    suffixes = [" inc.", " inc", " corp.", " corp", " llc.", " llc", " ltd.", " ltd"]
    cleaned = name.lower().strip()
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
    return cleaned

class EntityResolver:
    def __init__(self, canonical_list=SEED_STARTUPS):
        self.canonical_list = canonical_list
        # Pre-clean canonical names for faster matching
        self.cleaned_canonical = {clean_entity_name(name): name for name in canonical_list}

    def resolve(self, raw_name: str) -> str:
        """
        Maps a raw extracted entity name to a canonical name if it's a close match.
        Returns the canonical name, or the cleaned raw_name if no match is found.
        """
        cleaned_raw = clean_entity_name(raw_name)
        
        # Exact match after cleaning
        if cleaned_raw in self.cleaned_canonical:
            return self.cleaned_canonical[cleaned_raw]

        # Fuzzy match
        best_match = None
        highest_score = 0
        
        for cleaned_canon, original_canon in self.cleaned_canonical.items():
            score = fuzz.ratio(cleaned_raw, cleaned_canon)
            if score > highest_score:
                highest_score = score
                best_match = original_canon
                
        if highest_score >= 85: # Threshold for considering it a match
            return best_match
            
        return raw_name
