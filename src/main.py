"""
GraphOne Data Intelligence Pipeline
====================================
Entry point that orchestrates all scraping, LLM extraction,
entity resolution, and Excel export.
"""

import asyncio
import json
import logging
import os

import pandas as pd
from dotenv import load_dotenv

# Scrapers
from scraper.real_entity_scraper import RealEntityScraper
from scraper.arxiv_scraper import ArxivScraper
from scraper.paperswithcode_scraper import PapersWithCodeScraper
from scraper.news_jobs_scraper import NewsJobsScraper

# LLM + Entity
from llm_orchestrator.orchestrator import LLMOrchestrator
from entity_resolver.resolver import EntityResolver

# Utilities
from utils.freshness_cache import FreshnessCache

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_FILE = "GraphOne_Data_Output.xlsx"


# ── Helpers ────────────────────────────────────────────────────────────────────

def flatten_record(record: dict) -> dict:
    """Flatten nested JSON dicts into dot-notation columns for pandas."""
    flat: dict = {}

    def _flatten(obj, prefix=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                _flatten(v, f"{prefix}{k}." if prefix else f"{k}.")
        elif isinstance(obj, list):
            flat[prefix.rstrip(".")] = ", ".join(str(x) for x in obj)
        else:
            flat[prefix.rstrip(".")] = obj

    _flatten(record)
    return flat


def resolve_entities(records: list, field: str, resolver: EntityResolver) -> tuple[list, list]:
    """Apply entity resolution in-place and return (updated_records, mapping_log)."""
    mapping_log = []
    for rec in records:
        try:
            raw = rec["content"][field]
            canonical = resolver.resolve(raw)
            if raw != canonical:
                mapping_log.append({"Raw": raw, "Canonical": canonical})
                rec["content"][field] = canonical
        except (KeyError, TypeError):
            pass
    return records, mapping_log


# ── Pipeline stages ────────────────────────────────────────────────────────────

async def run_pipeline():
    load_dotenv()
    logger.info("═══ Starting GraphOne Data Intelligence Pipeline ═══")

    resolver = EntityResolver()
    cache = FreshnessCache()

    # ── Phase I : Bulk entity extraction ──────────────────────────────────────
    logger.info("Phase I → Extracting real Startups & Products")
    entity_scraper = RealEntityScraper(max_records=1000)
    startups, products = await asyncio.gather(
        entity_scraper.fetch_startups(),
        entity_scraper.fetch_products(),
    )

    logger.info(f"Phase I → Got {len(startups)} startups, {len(products)} products")

    # Entity-resolve startup names
    startups, startup_mappings = resolve_entities(startups, "entityName", resolver)
    products, product_mappings = resolve_entities(products, "startupName", resolver)

    # ── Phase I : Research Papers ─────────────────────────────────────────────
    logger.info("Phase I → Extracting Research Papers (HF Daily Papers + Arxiv)")

    pwc_scraper = PapersWithCodeScraper(max_results=700)
    arxiv_scraper = ArxivScraper(max_results=400)  # Supplement to reach 1000

    pwc_papers, arxiv_papers = await asyncio.gather(
        pwc_scraper.fetch_papers(),
        arxiv_scraper.fetch_papers(),
    )

    # Deduplicate by title — HF papers already include GitHub data, prefer them
    seen_titles = {p["content"]["title"].lower() for p in pwc_papers}
    for p in arxiv_papers:
        title = p.get("title", "")
        if title.lower() not in seen_titles:
            pwc_papers.append({
                "schemaVersion": "1.0",
                "recordType": "RESEARCH_PAPER",
                "content": {
                    "title": title,
                    "authors": p.get("authors", []),
                    "paper_url": p.get("paper_url", ""),
                    "github_url": p.get("github_url"),
                    "github_stars": p.get("github_stars"),
                    "published_date": p.get("published_date", ""),
                }
            })
            seen_titles.add(title.lower())
            if len(pwc_papers) >= 1000:
                break

    # Enrich only Arxiv-sourced papers that have a github_url but no star count
    papers_needing_stars = [
        p for p in pwc_papers
        if p["content"].get("github_url") and p["content"].get("github_stars") is None
    ]
    if papers_needing_stars:
        logger.info(f"Enriching {len(papers_needing_stars)} Arxiv papers with GitHub stars…")
        flat_for_enrichment = [
            {"github_url": p["content"]["github_url"], "github_stars": None}
            for p in papers_needing_stars
        ]
        await arxiv_scraper.enrich_github_stars(flat_for_enrichment)
        for i, p in enumerate(papers_needing_stars):
            p["content"]["github_stars"] = flat_for_enrichment[i]["github_stars"]

    papers = pwc_papers[:1000]
    logger.info(f"Phase I → Total {len(papers)} research papers ready.")


    # ── Phase II & III : News + Jobs (24-hr fresh) ────────────────────────────
    logger.info("Phase II → Fetching fresh News & Jobs (last 24 h)")
    news_jobs_scraper = NewsJobsScraper(cache=cache)

    news, raw_jobs = await asyncio.gather(
        news_jobs_scraper.fetch_recent_news(),
        news_jobs_scraper.fetch_recent_jobs(),
    )
    logger.info(f"Phase II → {len(news)} news articles | {len(raw_jobs)} raw job postings")

    # ── Phase III : Multi-Tier LLM Extraction Engine ────────────────────────
    logger.info("Phase III → Structuring raw job text via LLM Orchestrator...")
    orchestrator = LLMOrchestrator()
    JOB_SCHEMA = '''
    {
      "schemaVersion": "1.0",
      "recordType": "JOB",
      "content": {
        "company": "string (Canonical company name)",
        "date": "string (ISO-8601 publication date)",
        "is_remote": "boolean",
        "role_family": "string (Functional category e.g. Engineering)"
      }
    }
    '''
    
    jobs = []
    for raw_job in raw_jobs:
        try:
            # We pass the raw title/summary text to the LLM to extract strict JSON
            text_payload = f"Title: {raw_job['content']['title']}\nSummary: {raw_job['content'].get('raw_text', '')}"
            # chunking logic is natively handled by the LLM (or mock if no key)
            structured_json_str = await orchestrator.extract_structured_data(text_payload[:6000], JOB_SCHEMA)
            
            # The orchestrator handles Fallbacks. Parse the JSON:
            import json
            import re
            
            # Clean possible markdown formatting from LLM response
            clean_str = re.sub(r'```json\n?|```', '', structured_json_str).strip()
            parsed_job = json.loads(clean_str)
            
            # Restore the URL for traceability
            parsed_job["content"]["url"] = raw_job["content"]["url"]
            jobs.append(parsed_job)
        except Exception as e:
            logger.error(f"LLM extraction failed for job: {e}")
            # fallback to heuristic if LLM fails completely
            jobs.append(raw_job)


    # Entity-resolve company names in jobs
    jobs, job_mappings = resolve_entities(jobs, "company", resolver)

    # ── Aggregate mapping log ─────────────────────────────────────────────────
    all_mappings = startup_mappings + product_mappings + job_mappings

    # ── Export ────────────────────────────────────────────────────────────────
    logger.info(f"Exporting data to {OUTPUT_FILE}…")

    rows_startups  = [flatten_record(r) for r in startups]
    rows_products  = [flatten_record(r) for r in products]
    rows_papers    = [flatten_record(r) for r in papers]
    rows_jobs      = [flatten_record(r) for r in jobs]
    rows_news      = news  # already flat dicts

    with pd.ExcelWriter(OUTPUT_FILE, engine="openpyxl") as writer:
        pd.DataFrame(rows_startups).to_excel(writer, sheet_name="Startups",       index=False)
        pd.DataFrame(rows_products).to_excel(writer, sheet_name="Products",       index=False)
        pd.DataFrame(rows_papers).to_excel(  writer, sheet_name="Research Papers", index=False)
        pd.DataFrame(rows_jobs).to_excel(    writer, sheet_name="Jobs",           index=False)
        pd.DataFrame(rows_news).to_excel(    writer, sheet_name="News",           index=False)
        pd.DataFrame(all_mappings).to_excel( writer, sheet_name="Entity Mapping Log", index=False)

    logger.info(
        f"═══ Pipeline complete! ═══\n"
        f"  Startups       : {len(startups)}\n"
        f"  Products       : {len(products)}\n"
        f"  Research Papers: {len(papers)}\n"
        f"  Jobs (24 h)    : {len(jobs)}\n"
        f"  News (24 h)    : {len(news)}\n"
        f"  Entity Mappings: {len(all_mappings)}\n"
        f"  Output file    : {OUTPUT_FILE}"
    )

    cache.close()


if __name__ == "__main__":
    asyncio.run(run_pipeline())
