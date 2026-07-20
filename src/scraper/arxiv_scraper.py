import aiohttp
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
import re
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

class ArxivScraper:
    def __init__(self, max_results: int = 1000):
        self.max_results = max_results
        self.base_url = "http://export.arxiv.org/api/query"
        self.github_pattern = re.compile(r'https://github\.com/[a-zA-Z0-9-]+/[a-zA-Z0-9_.-]+')

    async def fetch_papers(self) -> List[Dict[str, Any]]:
        papers = []
        start = 0
        batch_size = 100
        
        async with aiohttp.ClientSession() as session:
            while len(papers) < self.max_results:
                params = {
                    "search_query": "cat:cs.AI OR cat:cs.CL OR cat:cs.CV OR cat:cs.LG",
                    "start": start,
                    "max_results": batch_size,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending"
                }
                
                try:
                    async with session.get(self.base_url, params=params) as response:
                        if response.status != 200:
                            logger.error(f"Arxiv API error: {response.status}")
                            break
                        
                        data = await response.text()
                        root = ET.fromstring(data)
                        
                        entries = root.findall('{http://www.w3.org/2005/Atom}entry')
                        if not entries:
                            break
                            
                        for entry in entries:
                            if len(papers) >= self.max_results:
                                break
                                
                            title = entry.find('{http://www.w3.org/2005/Atom}title').text.strip().replace('\n', ' ')
                            published = entry.find('{http://www.w3.org/2005/Atom}published').text
                            paper_url = entry.find('{http://www.w3.org/2005/Atom}id').text
                            summary = entry.find('{http://www.w3.org/2005/Atom}summary').text
                            
                            authors = []
                            for author in entry.findall('{http://www.w3.org/2005/Atom}author'):
                                name = author.find('{http://www.w3.org/2005/Atom}name').text
                                authors.append(name)
                                
                            # Extract Github URL from summary
                            github_url = None
                            match = self.github_pattern.search(summary)
                            if match:
                                github_url = match.group(0)
                                
                            papers.append({
                                "title": title,
                                "authors": authors,
                                "paper_url": paper_url,
                                "github_url": github_url,
                                "published_date": published,
                                "github_stars": None # To be enriched later
                            })
                            
                        start += batch_size
                        logger.info(f"Fetched {len(papers)} papers from Arxiv...")
                        await asyncio.sleep(3) # Respect Arxiv rate limits (3 secs between requests)
                except Exception as e:
                    logger.error(f"Failed to fetch batch starting at {start}: {e}")
                    break
                    
        return papers

    async def enrich_github_stars(self, papers: List[Dict[str, Any]]):
        """Enrich papers with GitHub stars."""
        # Using a semaphore to limit concurrent requests to GitHub API
        sem = asyncio.Semaphore(5)
        
        async def fetch_stars(session, paper):
            if not paper.get("github_url"):
                return
                
            # Extract owner/repo
            parts = paper["github_url"].split("github.com/")
            if len(parts) > 1:
                repo_path = parts[1].strip("/")
                api_url = f"https://api.github.com/repos/{repo_path}"
                
                async with sem:
                    try:
                        # Passing a dummy token if available, else unauthenticated (rate limited to 60/hr)
                        # We will handle 403 rate limit by just returning None
                        async with session.get(api_url) as response:
                            if response.status == 200:
                                data = await response.json()
                                paper["github_stars"] = data.get("stargazers_count")
                            elif response.status == 403:
                                # Rate limited
                                pass
                    except Exception:
                        pass
        
        async with aiohttp.ClientSession() as session:
            tasks = [fetch_stars(session, p) for p in papers if p.get("github_url")]
            if tasks:
                await asyncio.gather(*tasks)

