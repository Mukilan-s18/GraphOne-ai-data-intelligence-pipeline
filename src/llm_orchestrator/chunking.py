import tiktoken
from typing import List

def count_tokens(text: str, model: str = "cl100k_base") -> int:
    try:
        encoding = tiktoken.get_encoding(model)
        return len(encoding.encode(text))
    except Exception:
        # Fallback approximation
        return len(text.split())

def chunk_text(text: str, max_tokens: int = 6000, model: str = "cl100k_base") -> List[str]:
    """
    Intelligently chunks text by paragraphs to ensure we don't exceed context window limits.
    """
    if count_tokens(text, model) <= max_tokens:
        return [text]

    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""

    for p in paragraphs:
        if count_tokens(current_chunk + "\n\n" + p, model) > max_tokens:
            if current_chunk:
                chunks.append(current_chunk.strip())
            current_chunk = p
        else:
            current_chunk += "\n\n" + p

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks
