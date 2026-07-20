# GraphOne Data Intelligence Architecture

## 1. Scale Strategy (500k+ Records)
To scale this architecture to acquire hundreds of thousands of startups, products, and research papers without manual intervention, a distributed crawler infrastructure is essential.
- **Message Queues & Microservices:** The scraping engine will be decoupled into isolated microservices communicating via message queues (e.g., Kafka or RabbitMQ, using Celery). The URL discovery engine feeds URLs into a `ScrapeQueue`.
- **Horizontal Scaling:** Worker nodes consume URLs from the `ScrapeQueue`. As load increases or target sites scale, we can horizontally auto-scale worker pods in a Kubernetes cluster.
- **Proxy Networks & IP Rotation:** For massive bulk extraction against protected directories (Cloudflare, Datadome), workers will route traffic through rotating residential and mobile proxy networks (e.g., BrightData, Oxylabs). Playwright with `playwright-stealth` or `curl_cffi` ensures JA3/TLS fingerprint impersonation.

## 2. Handling 413s (Context Overflows) and 429s (Rate Limits)
- **413 Payload Too Large:** We employ Intelligent Chunking using `tiktoken`. Raw HTML or text is segmented at paragraph or semantic boundaries to fit within the strictest LLM context window (e.g., 6000 tokens). Each chunk is processed individually, and results are merged.
- **429 Too Many Requests:** The `LLMOrchestrator` implements a robust multi-tier fallback chain (Gemini Flash → Groq Llama 3 → DeepSeek). If a provider responds with a 429, the system automatically retries with exponential backoff and jitter (via the `tenacity` library). If limits persist, it gracefully falls back to the next provider in the chain.

## 3. Freshness Tracking
To guarantee 24-hour freshness and prevent processing duplicates across distributed crawler nodes:
- **Distributed Cache:** A Redis cluster acts as the central state store for all distributed nodes, utilizing Bloom Filters for ultra-fast "URL seen" or "Content Hash seen" lookups. 
- **Content Hashing (MD5/SHA-256):** Even if URLs change, hashing the raw text ensures duplicate articles are ignored.
- **Heuristic Deduplication:** For sources lacking strict dates, if the URL or Content Hash does not exist in the Redis Bloom Filter, it is flagged as a "new" signal and processed.

## 4. Storage Strategy
- **Primary Database (PostgreSQL):** A highly relational model is optimal for the structured canonical schemas. PostgreSQL, equipped with JSONB columns for flexible data storage and indexing, will serve as the source of truth for standard entities.
- **Vector/Graph Storage:** 
  - **Vector Storage (Pinecone or Qdrant):** Embeddings of raw text descriptions will be stored here to enable semantic search across startups and research papers.
  - **Graph Storage (Neo4j):** To map complex, multi-dimensional relationships (e.g., Founder -> Startup -> Product <- Competitor), a graph database like Neo4j will map relationships dynamically, powering the ultimate Intelligence Graph.
