import pytest
import os
import tempfile
from datetime import datetime, timedelta
from src.utils.freshness_cache import FreshnessCache

@pytest.fixture
def cache_db():
    fd, path = tempfile.mkstemp()
    os.close(fd)
    cache = FreshnessCache(db_path=path)
    yield cache
    cache.close()
    if os.path.exists(path):
        os.unlink(path)

def test_cache_initial_url_is_not_seen(cache_db):
    # A new URL should not be seen
    assert cache_db.is_seen("http://example.com/1") == False

def test_cache_seen_url_is_seen(cache_db):
    # After marking it, it should be seen
    cache_db.mark_seen("http://example.com/2")
    assert cache_db.is_seen("http://example.com/2") == True

def test_cache_different_urls(cache_db):
    cache_db.mark_seen("http://example.com/3")
    assert cache_db.is_seen("http://example.com/3") == True
    assert cache_db.is_seen("http://example.com/4") == False
