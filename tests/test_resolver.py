import pytest
from src.entity_resolver.resolver import EntityResolver, clean_entity_name

def test_clean_entity_name():
    assert clean_entity_name("OpenAI Inc.") == "openai"
    assert clean_entity_name("  OpenAI, Corp  ") == "openai,"
    assert clean_entity_name("DeepMind LLC") == "deepmind"

def test_resolver_exact_match():
    resolver = EntityResolver(["OpenAI", "DeepMind", "Anthropic"])
    assert resolver.resolve("OpenAI") == "OpenAI"
    assert resolver.resolve("DeepMind Inc.") == "DeepMind"
    assert resolver.resolve("anthropic") == "Anthropic"

def test_resolver_fuzzy_match():
    resolver = EntityResolver(["Hugging Face", "Stability AI"])
    # Should resolve despite minor typos
    assert resolver.resolve("HuggingFace") == "Hugging Face"
    assert resolver.resolve("StabilityAI") == "Stability AI"

def test_resolver_no_match():
    resolver = EntityResolver(["OpenAI", "DeepMind"])
    # Should not resolve if it's completely different
    assert resolver.resolve("Random Startup") == "Random Startup"
