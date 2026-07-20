# GraphOne Data Intelligence Pipeline

This repository contains the solution for the GraphOne (Atlas Intelligence) AI Engineer trial assignment.
It demonstrates a resilient, highly concurrent, and production-ready data pipeline capable of one-time bulk acquisition, LLM-based entity structuring, and deterministic entity resolution.

## Project Structure
- `src/main.py`: The entry point for the pipeline.
- `src/scraper/`: Contains specialized and generic async scrapers (Arxiv, News/Jobs, Startups/Products).
- `src/llm_orchestrator/`: Implements a multi-tier fallback chain (Gemini -> Groq -> DeepSeek) and intelligent token chunking.
- `src/entity_resolver/`: Implements deterministic fuzzy matching against a seed list of known canonical AI entities.
- `src/schemas.py`: Canonical JSON schemas defined using Pydantic.

## Setup Instructions

### Option 1: Docker (Recommended for Reviewers)
The easiest way to run the entire pipeline is via Docker Compose. It will automatically build the environment, install dependencies, and start the FastAPI wrapper on port 8000.
```bash
docker-compose up --build
```
You can then trigger the pipeline by navigating to `http://localhost:8000/docs` and executing the `/trigger` POST route, or by running:
```bash
curl -X POST http://localhost:8000/trigger
```

### Option 2: Local Python Environment
1. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Create a `.env` file in the root directory and add your LLM API keys:
   ```
   GEMINI_API_KEY=your_gemini_key
   GROQ_API_KEY=your_groq_key
   DEEPSEEK_API_KEY=your_deepseek_key
   ```
   *Note: If no API keys are provided, the pipeline will utilize a mock LLM fallback to ensure successful execution.*

3. Run the pipeline directly:
   ```bash
   cd src
   python main.py
   ```
   Or run the FastAPI server:
   ```bash
   uvicorn src.api:app --reload
   ```

### Unit Tests
This project uses `pytest` for rigorous testing of core logic (entity resolution, LLM chunking, freshness cache).
```bash
PYTHONPATH=$(pwd) pytest tests/ -v
```

## Architecture Overview

**1. Massive One-Time Data Acquisition (Phase I)**
   - Utilizes highly concurrent `asyncio` + `aiohttp` pipelines with bounded semaphores to fetch 1,000+ Startups (from GitHub Awesome lists), 1,000+ Products (ai-collection/HF Spaces), and 1,000+ Papers (HF Daily Papers/Arxiv).

**2. High-Fidelity Signal Ingestion (Phase II)**
   - Scrapes 5 distinct AI news sources and 5 distinct AI job boards via RSS and JSON feeds. Enforces a strict 24-hour freshness heuristic.
   - Extracts full text using `BeautifulSoup` and tracks freshness via a local SQLite URL cache (`FreshnessCache`).

**3. Multi-Tier LLM Extraction Engine (Phase III)**
   - To transform raw HTML/text into canonical JSON schemas without triggering 413s, payloads are semantically chunked using `tiktoken` by paragraph.
   - The orchestrator chains fallback LLM calls (Gemini ➔ Groq ➔ DeepSeek) with `tenacity` exponential jitter for robust 429 backoff handling.

**4. Deterministic Entity Resolution (Phase IV)**
   - Uses `fuzzywuzzy` Levenshtein distance (≥ 85% confidence) against a seeded dictionary of 50 canonical AI entities to map messy extracted names (e.g., "OpenAI Inc.") into pristine entities (e.g., "OpenAI").

**5. Anti-Bot Strategy**
   - For heavily JS-rendered sites, architecture design covers `curl_cffi` TLS fingerprinting and headless `Playwright`.

## Deliverables
- Upon successful execution, the pipeline outputs a Microsoft Excel workbook (`GraphOne_Data_Output.xlsx`) containing 6 tabs: Startups, Products, Research Papers, Jobs, News, and Entity Mapping Log.
- You can directly import this `.xlsx` file into Google Sheets.
- The `architecture.pdf` is provided in this repository for detailed design documentation.
