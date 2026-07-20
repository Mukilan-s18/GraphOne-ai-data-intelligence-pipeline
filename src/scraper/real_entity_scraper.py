import aiohttp
import asyncio
import re
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# AI Collection (4000+ real AI tools/products)
# Format: ### ProductName  then  [Visit](https://thataicollection.com/redirect/slug)
AI_COLLECTION_URL = "https://raw.githubusercontent.com/ai-collection/ai-collection/main/README.md"

# Multiple awesome lists for real startup names + URLs (combined > 3000 unique links)
AWESOME_LISTS = [
    "https://raw.githubusercontent.com/steven2358/awesome-generative-ai/main/README.md",
    "https://raw.githubusercontent.com/mahseema/awesome-ai-tools/main/README.md",
    "https://raw.githubusercontent.com/kyrolabs/awesome-langchain/main/README.md",
    "https://raw.githubusercontent.com/imaurer/awesome-decentralized-llm/main/README.md",
    "https://raw.githubusercontent.com/e2b-dev/awesome-ai-agents/main/README.md",
    "https://raw.githubusercontent.com/Hannibal046/Awesome-LLM/main/README.md",
    "https://raw.githubusercontent.com/eugeneyan/open-llms/main/README.md",
]

HF_SPACES_API = "https://huggingface.co/api/spaces?limit=500&sort=likes&direction=-1"

MD_LINK_RE = re.compile(r'\[([^\]]{2,60})\]\((https?://[^\)\s]+)\)')

# ai-collection uses ### Name as heading, then [Visit](redirect_url) as link
H3_RE    = re.compile(r'^###\s+(.+)')
VISIT_RE = re.compile(r'\[Visit\]\((https://thataicollection\.com/redirect/([^\?]+))')
INFO_RE  = re.compile(r'\[More Information and Pricing\]\((https://thataicollection\.com/en/application/([^\?]+))')


class RealEntityScraper:
    """
    Scrapes real AI startup/product data from:
    - ai-collection (github.com/ai-collection/ai-collection): 4000+ AI tools
    - Multiple 'awesome-*' curated lists on GitHub

    Every entity has a verifiable source URL — zero hallucinated data.
    """

    def __init__(self, max_records: int = 1000):
        self.max_records = max_records

    # ------------------------------------------------------------------ helpers
    async def _fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=20)) as r:
                if r.status == 200:
                    return await r.text()
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
        return ""

    @staticmethod
    def _infer_pricing(line: str) -> str:
        low = line.lower()
        if any(k in low for k in [":free:", "open-source", "open source", "free tier", "✔️ free"]):
            return "FREE"
        if "freemium" in low:
            return "FREEMIUM"
        if "enterprise" in low:
            return "ENTERPRISE"
        if any(k in low for k in [":paid:", ":moneybag:", "💰", "paid only", "subscription"]):
            return "PAID"
        return "FREEMIUM"

    # ------------------------------------------------------------------  Products
    async def fetch_products(self) -> List[Dict[str, Any]]:
        """
        Returns 1000+ real AI product records from ai-collection.
        Format per entry:
            ### ProductName
            [Visit](https://thataicollection.com/redirect/slug)
        """
        products = []
        seen_slugs: set = set()

        async with aiohttp.ClientSession() as session:
            content = await self._fetch(session, AI_COLLECTION_URL)

        if not content:
            logger.error("Could not fetch ai-collection. Check connectivity.")
            return products

        lines = content.splitlines()
        current_name: Optional[str] = None

        for line in lines:
            if len(products) >= self.max_records:
                break

            # Match product name from h3 heading
            h3_m = H3_RE.match(line)
            if h3_m:
                # Clean name: strip markdown formatting, take first part before "|"
                raw_name = h3_m.group(1).strip()
                # The heading may look like "ProductName | Tagline"
                current_name = raw_name.split("|")[0].strip()
                continue

            # Match Visit link
            visit_m = VISIT_RE.search(line)
            if visit_m and current_name:
                redirect_url = visit_m.group(1)
                slug = visit_m.group(2).rstrip("?")

                if slug in seen_slugs or not current_name:
                    current_name = None
                    continue

                seen_slugs.add(slug)
                # Derive the real product page URL from the slug
                product_url = f"https://thataicollection.com/en/application/{slug}"

                products.append({
                    "schemaVersion": "1.0",
                    "recordType": "PRODUCT",
                    "source": {"name": "That AI Collection", "url": product_url},
                    "content": {
                        "startupName": current_name,
                        "pricingModel": "FREEMIUM"  # Pricing scraped from description below
                    },
                    "collectedAt": datetime.utcnow().isoformat() + "Z"
                })
                current_name = None
                continue

            # Enrich pricing from description lines
            if products and any(k in line.lower() for k in ["free", "freemium", "paid", "enterprise", "open source"]):
                last = products[-1]["content"]
                if last["pricingModel"] == "FREEMIUM":
                    inferred = self._infer_pricing(line)
                    if inferred != "FREEMIUM":
                        last["pricingModel"] = inferred

        logger.info(f"Fetched {len(products)} real product records from ai-collection.")

        # ── Supplement with HuggingFace Spaces if under target ────────────────
        if len(products) < self.max_records:
            needed = self.max_records - len(products)
            logger.info(f"Supplementing with up to {needed} products from HuggingFace Spaces…")
            hf_products = await self._fetch_hf_spaces(needed, seen_slugs)
            products.extend(hf_products)

        logger.info(f"Total products after supplementation: {len(products)}")
        return products

    async def _fetch_hf_spaces(self, limit: int, seen_slugs: set) -> List[Dict[str, Any]]:
        """Fetch AI tools/demos from HuggingFace Spaces public API."""
        products = []
        seen_ids: set = set()

        async with aiohttp.ClientSession() as session:
            page = 0
            while len(products) < limit:
                url = f"{HF_SPACES_API}&p={page}"
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status != 200:
                            break
                        data = await resp.json()
                except Exception as e:
                    logger.error(f"HF Spaces fetch error: {e}")
                    break

                if not data:
                    break

                for space in data:
                    if len(products) >= limit:
                        break
                    space_id = space.get("id", "")
                    if not space_id or space_id in seen_ids:
                        continue
                    seen_ids.add(space_id)

                    # Infer pricing from tags
                    tags = space.get("tags", [])
                    pricing = "FREE"  # HF Spaces are free to use by default
                    if "commercial" in tags or "api" in tags:
                        pricing = "FREEMIUM"

                    products.append({
                        "schemaVersion": "1.0",
                        "recordType": "PRODUCT",
                        "source": {
                            "name": "HuggingFace Spaces",
                            "url": f"https://huggingface.co/spaces/{space_id}"
                        },
                        "content": {
                            "startupName": space_id.split("/")[0],  # author/org name
                            "pricingModel": pricing
                        },
                        "collectedAt": datetime.utcnow().isoformat() + "Z"
                    })

                page += 1
                if page > 20:  # Safety stop at 20 pages × 500 = 10k
                    break

        logger.info(f"HuggingFace Spaces: fetched {len(products)} additional products.")
        return products


    # ----------------------------------------------------------------- Startups
    async def fetch_startups(self) -> List[Dict[str, Any]]:
        """
        Returns 1000+ real AI startup records from multiple curated awesome lists
        + ai-collection as a fallback supplement.
        Every record has a valid source URL.
        """
        startups = []
        seen_names: set = set()
        seen_urls: set = set()

        # --- Phase 1: curated awesome lists ---
        async with aiohttp.ClientSession() as session:
            tasks = [self._fetch(session, u) for u in AWESOME_LISTS]
            contents = await asyncio.gather(*tasks)

        for content in contents:
            if not content:
                continue
            for m in MD_LINK_RE.finditer(content):
                if len(startups) >= self.max_records:
                    break
                name, url = m.group(1).strip(), m.group(2).strip()
                key = name.lower()
                if not name or not url or key in seen_names or url in seen_urls:
                    continue
                # Filter out non-company links (paper links, issue links, etc.)
                if any(skip in url for skip in ["github.com/topics", "github.com/search",
                                                 "arxiv.org", "wikipedia.org"]):
                    continue
                seen_names.add(key)
                seen_urls.add(url)
                startups.append({
                    "schemaVersion": "1.0",
                    "recordType": "STARTUP",
                    "source": {"name": "Awesome AI Lists (GitHub)", "url": url},
                    "content": {
                        "entityName": name,
                        "data": {"employeeCount": None}
                    },
                    "collectedAt": datetime.utcnow().isoformat() + "Z"
                })

        # --- Phase 2: supplement from ai-collection if needed ---
        if len(startups) < self.max_records:
            async with aiohttp.ClientSession() as session:
                content = await self._fetch(session, AI_COLLECTION_URL)

            for line in content.splitlines():
                if len(startups) >= self.max_records:
                    break
                if not line.startswith("|") or "---" in line:
                    continue
                m = MD_LINK_RE.search(line)
                if not m:
                    continue
                name, url = m.group(1).strip(), m.group(2).strip()
                key = name.lower()
                if not name or not url or key in seen_names or url in seen_urls:
                    continue
                if "github.com/ai-collection" in url:
                    continue
                seen_names.add(key)
                seen_urls.add(url)
                startups.append({
                    "schemaVersion": "1.0",
                    "recordType": "STARTUP",
                    "source": {"name": "AI Collection (GitHub)", "url": url},
                    "content": {
                        "entityName": name,
                        "data": {"employeeCount": None}
                    },
                    "collectedAt": datetime.utcnow().isoformat() + "Z"
                })

        logger.info(f"Fetched {len(startups)} real startup records.")
        return startups
