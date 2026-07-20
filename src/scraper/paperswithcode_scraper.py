"""
HuggingFace Daily Papers scraper.
Replaces the PapersWithCode scraper (which now redirects to HuggingFace anyway).

API endpoint: https://huggingface.co/api/daily_papers?date=YYYY-MM-DD
- Completely public, no auth required
- Returns papers curated by the community each day
- Already includes githubRepo URL and githubStars count
- ~15-25 papers per day → ~60 days needed for 1,000 papers
"""

import aiohttp
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

BASE_DATE = datetime(2025, 7, 18)  # Start from a known recent date


class PapersWithCodeScraper:
    """
    Fetches AI/ML research papers from Hugging Face Daily Papers API.
    Each paper includes title, authors, Arxiv ID, GitHub repo URL, and star count.
    """

    API_BASE = "https://huggingface.co/api/daily_papers"

    def __init__(self, max_results: int = 1000):
        self.max_results = max_results

    async def fetch_papers(self) -> List[Dict[str, Any]]:
        papers: List[Dict[str, Any]] = []
        seen_ids: set = set()

        async with aiohttp.ClientSession() as session:
            day_offset = 0
            while len(papers) < self.max_results:
                date_str = (BASE_DATE - timedelta(days=day_offset)).strftime("%Y-%m-%d")
                url = f"{self.API_BASE}?date={date_str}"

                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                        if resp.status != 200:
                            logger.warning(f"HF Papers API returned {resp.status} for {date_str}")
                            day_offset += 1
                            if day_offset > 90:  # Safety stop
                                break
                            continue

                        data = await resp.json()

                except Exception as e:
                    logger.error(f"HF Papers fetch error for {date_str}: {e}")
                    day_offset += 1
                    continue

                if not data:
                    day_offset += 1
                    if day_offset > 90:
                        break
                    continue

                for item in data:
                    if len(papers) >= self.max_results:
                        break

                    paper = item.get("paper", {})
                    arxiv_id = paper.get("id", "")
                    if not arxiv_id or arxiv_id in seen_ids:
                        continue

                    seen_ids.add(arxiv_id)

                    title = paper.get("title", "").strip()
                    if not title:
                        continue

                    authors = [
                        a.get("name", a.get("user", {}).get("fullname", ""))
                        for a in paper.get("authors", [])
                        if isinstance(a, dict)
                    ]
                    authors = [a for a in authors if a]

                    paper_url = f"https://arxiv.org/abs/{arxiv_id}"

                    github_url: Optional[str] = paper.get("githubRepo") or None
                    github_stars_raw = paper.get("githubStars")
                    github_stars: Optional[int] = None
                    if github_stars_raw is not None:
                        try:
                            github_stars = int(github_stars_raw)
                        except (ValueError, TypeError):
                            pass

                    published_raw = paper.get("publishedAt", item.get("publishedAt", ""))
                    try:
                        published_date = datetime.fromisoformat(
                            published_raw.replace("Z", "+00:00")
                        ).isoformat()
                    except Exception:
                        published_date = published_raw

                    papers.append({
                        "schemaVersion": "1.0",
                        "recordType": "RESEARCH_PAPER",
                        "content": {
                            "title": title,
                            "authors": authors,
                            "paper_url": paper_url,
                            "github_url": github_url,
                            "github_stars": github_stars,
                            "published_date": published_date,
                        }
                    })

                logger.info(
                    f"HF Daily Papers: {date_str} → {len(data)} items "
                    f"(total collected: {len(papers)})"
                )
                day_offset += 1
                await asyncio.sleep(0.3)

        logger.info(f"HF Daily Papers: finished with {len(papers)} papers.")
        return papers[:self.max_results]
