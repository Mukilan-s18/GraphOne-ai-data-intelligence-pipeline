import feedparser
import aiohttp
import asyncio
import re
from bs4 import BeautifulSoup
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dateutil import parser as dateutil_parser
import pytz

from utils.freshness_cache import FreshnessCache

logger = logging.getLogger(__name__)

# ── Sources ────────────────────────────────────────────────────────────────────
NEWS_FEEDS = [
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://www.artificialintelligence-news.com/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://machinelearningmastery.com/blog/feed/",
    "https://bair.berkeley.edu/blog/feed.xml",
]

JOB_FEEDS = [
    "https://weworkremotely.com/categories/remote-programming-jobs.rss",
    "https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss",
    "https://aijobs.net/feed/",
    "https://remoteok.com/feed",
    "https://hnrss.org/jobs",
]

RELATIVE_DATE_PATTERNS = [
    (re.compile(r'(\d+)\s+second', re.I),  lambda m: timedelta(seconds=int(m.group(1)))),
    (re.compile(r'(\d+)\s+minute', re.I),  lambda m: timedelta(minutes=int(m.group(1)))),
    (re.compile(r'(\d+)\s+hour',   re.I),  lambda m: timedelta(hours=int(m.group(1)))),
    (re.compile(r'(\d+)\s+day',    re.I),  lambda m: timedelta(days=int(m.group(1)))),
    (re.compile(r'(\d+)\s+week',   re.I),  lambda m: timedelta(weeks=int(m.group(1)))),
    (re.compile(r'yesterday',      re.I),  lambda m: timedelta(days=1)),
    (re.compile(r'just\s+now|moments?\s+ago', re.I), lambda m: timedelta(seconds=0)),
]

# ── Role-family classifier ────────────────────────────────────────────────────
ROLE_KEYWORDS: Dict[str, List[str]] = {
    "Engineering":  ["engineer", "developer", "software", "backend", "frontend",
                     "fullstack", "devops", "sre", "infrastructure", "platform"],
    "Research":     ["research", "scientist", "ml", "machine learning", "deep learning",
                     "nlp", "computer vision", "reinforcement"],
    "Data":         ["data", "analyst", "analytics", "bi", "pipeline", "etl"],
    "Product":      ["product manager", "pm ", " pm,", "program manager", "product owner"],
    "Design":       ["design", "ux", "ui ", "user experience", "creative"],
    "Sales":        ["sales", "account executive", "business development", "revenue", "growth"],
    "Marketing":    ["marketing", "content", "seo", "brand", "copywriter"],
    "Operations":   ["operations", "support", "customer success", "office", "hr", "recruit"],
    "Management":   ["director", "vp ", "vice president", "head of", "chief", "cto", "ceo"],
}

def classify_role_family(title: str) -> str:
    lower = title.lower()
    for family, keywords in ROLE_KEYWORDS.items():
        if any(k in lower for k in keywords):
            return family
    return "Other"


class NewsJobsScraper:
    def __init__(
        self,
        cache: Optional[FreshnessCache] = None,
        news_hours: int = 24,
        jobs_hours: int = 24,
    ):
        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        self.news_cutoff = now_utc - timedelta(hours=news_hours)
        self.jobs_cutoff = now_utc - timedelta(hours=jobs_hours)
        self.cutoff_time = self.news_cutoff  # default for backward compat
        self.cache = cache or FreshnessCache()

    # ── Date parsing ──────────────────────────────────────────────────────────
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        if not date_str:
            return None

        now_utc = datetime.utcnow().replace(tzinfo=pytz.UTC)
        text = date_str.strip()

        # Try relative patterns first ("2 hours ago", "yesterday", …)
        for pattern, delta_fn in RELATIVE_DATE_PATTERNS:
            m = pattern.search(text)
            if m:
                return now_utc - delta_fn(m)

        # Try standard ISO / RFC parsing
        try:
            dt = dateutil_parser.parse(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=pytz.UTC)
            return dt
        except Exception:
            return None

    def _is_fresh(self, date_str: str, url: str, cutoff: Optional[datetime] = None) -> bool:
        """
        Returns True if the item is within the freshness window.
        Fallback heuristic: if no parseable date, treat URL as fresh if never seen before.
        """
        effective_cutoff = cutoff or self.news_cutoff
        dt = self._parse_date(date_str)
        if dt is not None:
            return dt >= effective_cutoff
        # Heuristic: treat as fresh only if URL has not been seen before
        return not self.cache.is_seen(url)

    # ── Full-text fetch ───────────────────────────────────────────────────────
    async def _fetch_full_text(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    for tag in soup(["script", "style", "nav", "footer", "header"]):
                        tag.decompose()
                    return soup.get_text(separator=" ", strip=True)[:12000]
        except Exception as e:
            logger.debug(f"Full-text fetch failed for {url}: {e}")
        return ""

    # ── News ──────────────────────────────────────────────────────────────────
    async def fetch_recent_news(self) -> List[Dict[str, Any]]:
        recent_news = []
        async with aiohttp.ClientSession() as session:
            for feed_url in NEWS_FEEDS:
                logger.info(f"Fetching news from {feed_url}")
                try:
                    feed = feedparser.parse(feed_url)
                except Exception as e:
                    logger.error(f"Feed parse error {feed_url}: {e}")
                    continue

                for entry in feed.entries:
                    url = getattr(entry, "link", "")
                    date_str = entry.get("published", entry.get("updated", ""))

                    if not self._is_fresh(date_str, url):
                        continue
                    if self.cache.is_seen(url):
                        continue

                    full_text = await self._fetch_full_text(session, url)
                    self.cache.mark_seen(url)

                    recent_news.append({
                        "title": getattr(entry, "title", ""),
                        "url": url,
                        "published_date": (self._parse_date(date_str) or datetime.utcnow().replace(tzinfo=pytz.UTC)).isoformat(),
                        "full_text": full_text,
                    })

        logger.info(f"Collected {len(recent_news)} fresh news articles.")
        return recent_news

    # ── Jobs ──────────────────────────────────────────────────────────────────
    async def fetch_recent_jobs(self) -> List[Dict[str, Any]]:
        recent_jobs: List[Dict[str, Any]] = []

        async with aiohttp.ClientSession() as session:
            # ── RSS job boards ──
            for feed_url in JOB_FEEDS:
                logger.info(f"Fetching jobs from {feed_url}")
                try:
                    feed = feedparser.parse(feed_url)
                except Exception as e:
                    logger.error(f"Job feed parse error {feed_url}: {e}")
                    continue

                for entry in feed.entries:
                    url = getattr(entry, "link", "")
                    date_str = entry.get("published", entry.get("updated", ""))

                    if not self._is_fresh(date_str, url, cutoff=self.jobs_cutoff):
                        continue
                    if self.cache.is_seen(url):
                        continue

                    title = getattr(entry, "title", "")
                    self.cache.mark_seen(url)

                    recent_jobs.append({
                        "schemaVersion": "1.0",
                        "recordType": "JOB",
                        "content": {
                            "company": entry.get("author", "Unknown Company"),
                            "date": (self._parse_date(date_str) or datetime.utcnow().replace(tzinfo=pytz.UTC)).isoformat(),
                            "is_remote": (
                                "remote" in title.lower()
                                or "remote" in url.lower()
                                or "remote" in entry.get("summary", "").lower()
                            ),
                            "role_family": classify_role_family(title),
                            "title": title,
                            "url": url,
                            "raw_text": entry.get("summary", title)
                        }
                    })

            # ── Remotive JSON API ──
            try:
                remotive_url = "https://remotive.com/api/remote-jobs?category=software-dev"
                async with session.get(remotive_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for job in data.get("jobs", []):
                            url = job.get("url", "")
                            date_str = job.get("publication_date", "")

                            if not self._is_fresh(date_str, url, cutoff=self.jobs_cutoff):
                                continue
                            if self.cache.is_seen(url):
                                continue

                            title = job.get("title", "")
                            self.cache.mark_seen(url)

                            recent_jobs.append({
                                "schemaVersion": "1.0",
                                "recordType": "JOB",
                                "content": {
                                    "company": job.get("company_name", ""),
                                    "date": (self._parse_date(date_str) or datetime.utcnow().replace(tzinfo=pytz.UTC)).isoformat(),
                                    "is_remote": True,
                                    "role_family": classify_role_family(title),
                                    "title": title,
                                    "url": url,
                                    "raw_text": job.get("description", title)
                                }
                            })
            except Exception as e:
                logger.error(f"Remotive API error: {e}")

        logger.info(f"Collected {len(recent_jobs)} fresh job postings.")
        return recent_jobs
