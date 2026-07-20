import pytest
from src.llm_orchestrator.orchestrator import LLMOrchestrator

def test_intelligent_chunking_short_text():
    orchestrator = LLMOrchestrator()
    text = "This is a short text.\n\nIt has two paragraphs."
    chunked = orchestrator._intelligent_chunk(text, max_tokens=100)
    assert chunked == text

def test_intelligent_chunking_long_text():
    orchestrator = LLMOrchestrator()
    # Create a long text with multiple paragraphs
    p1 = "Paragraph one is relatively short."
    p2 = ("Paragraph two " * 100).strip() # Approx 200 tokens
    p3 = ("Paragraph three " * 100).strip() # Approx 200 tokens
    
    text = f"{p1}\n\n{p2}\n\n{p3}"
    
    # Restrict max tokens to just barely fit p1 and p2 (approx 200 tokens)
    chunked = orchestrator._intelligent_chunk(text, max_tokens=300)
    
    assert p1 in chunked
    assert p2 in chunked
    assert p3 not in chunked # Should be truncated

def test_intelligent_chunking_fallback(monkeypatch):
    # Temporarily remove tiktoken to test fallback logic
    import sys
    monkeypatch.setitem(sys.modules, "tiktoken", None)
    
    orchestrator = LLMOrchestrator()
    text = "A" * 1000
    chunked = orchestrator._intelligent_chunk(text, max_tokens=50)
    
    # Fallback should do basic string slicing: max_tokens * 4
    assert len(chunked) == 200
