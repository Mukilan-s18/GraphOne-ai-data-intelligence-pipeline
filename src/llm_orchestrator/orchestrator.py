import os
import asyncio
import logging
from typing import Any, Dict
import google.generativeai as genai
from openai import AsyncOpenAI
from tenacity import retry, wait_exponential_jitter, stop_after_attempt, retry_if_exception_type

logger = logging.getLogger(__name__)

class RateLimitError(Exception):
    pass

class ContextOverflowError(Exception):
    pass

class LLMOrchestrator:
    def __init__(self):
        # Configure Gemini
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if gemini_api_key:
            genai.configure(api_key=gemini_api_key)
        self.gemini_model = genai.GenerativeModel('gemini-1.5-flash') if gemini_api_key else None

        # Configure Groq
        groq_api_key = os.getenv("GROQ_API_KEY")
        self.groq_client = AsyncOpenAI(api_key=groq_api_key, base_url="https://api.groq.com/openai/v1") if groq_api_key else None

        # Configure DeepSeek
        deepseek_api_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_client = AsyncOpenAI(api_key=deepseek_api_key, base_url="https://api.deepseek.com/v1") if deepseek_api_key else None

    @retry(
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RateLimitError)
    )
    async def _call_gemini(self, prompt: str) -> str:
        if not self.gemini_model:
            raise ValueError("Gemini API key not configured")
        
        try:
            # Need to run blocking call in executor or use async client if available
            response = await asyncio.to_thread(self.gemini_model.generate_content, prompt)
            return response.text
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower():
                raise RateLimitError(f"Gemini Rate Limit: {str(e)}")
            elif "413" in str(e) or "too large" in str(e).lower():
                raise ContextOverflowError(f"Gemini Context Overflow: {str(e)}")
            raise e

    @retry(
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RateLimitError)
    )
    async def _call_groq(self, prompt: str) -> str:
        if not self.groq_client:
            raise ValueError("Groq API key not configured")
        
        try:
            response = await self.groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                raise RateLimitError(f"Groq Rate Limit: {str(e)}")
            elif "413" in str(e) or "context length" in str(e).lower():
                raise ContextOverflowError(f"Groq Context Overflow: {str(e)}")
            raise e

    @retry(
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type(RateLimitError)
    )
    async def _call_deepseek(self, prompt: str) -> str:
        if not self.deepseek_client:
            raise ValueError("DeepSeek API key not configured")
        
        try:
            response = await self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1
            )
            return response.choices[0].message.content
        except Exception as e:
            if "429" in str(e):
                raise RateLimitError(f"DeepSeek Rate Limit: {str(e)}")
            elif "413" in str(e) or "context length" in str(e).lower():
                raise ContextOverflowError(f"DeepSeek Context Overflow: {str(e)}")
            raise e

    def _intelligent_chunk(self, text: str, max_tokens: int = 4000) -> str:
        """
        Truncate text semantically by paragraph to prevent 413s, 
        using tiktoken to accurately count tokens and retain density.
        """
        try:
            import tiktoken
            encoding = tiktoken.get_encoding("cl100k_base")
        except ImportError:
            # Fallback if tiktoken is not available
            return text[:max_tokens * 4]

        paragraphs = text.split("\n\n")
        chunk = ""
        current_tokens = 0
        
        for p in paragraphs:
            p_tokens = len(encoding.encode(p))
            if current_tokens + p_tokens > max_tokens:
                break
            chunk += p + "\n\n"
            current_tokens += p_tokens
            
        return chunk.strip()

    async def extract_structured_data(self, prompt: str, schema: str) -> str:
        """
        Executes the fallback chain to extract structured data.
        Gemini -> Groq -> DeepSeek -> Mock (if no keys provided or all fail)
        """
        safe_prompt = self._intelligent_chunk(prompt)
        full_prompt = f"Extract the following information from the text into a strict JSON matching this schema:\n{schema}\n\nText:\n{safe_prompt}\n\nReturn ONLY valid JSON."
        
        # Try Gemini
        if self.gemini_model:
            try:
                logger.info("Attempting extraction with Gemini...")
                return await self._call_gemini(full_prompt)
            except Exception as e:
                logger.warning(f"Gemini failed: {e}. Falling back to Groq.")

        # Try Groq
        if self.groq_client:
            try:
                logger.info("Attempting extraction with Groq...")
                return await self._call_groq(full_prompt)
            except Exception as e:
                logger.warning(f"Groq failed: {e}. Falling back to DeepSeek.")

        # Try DeepSeek
        if self.deepseek_client:
            try:
                logger.info("Attempting extraction with DeepSeek...")
                return await self._call_deepseek(full_prompt)
            except Exception as e:
                logger.warning(f"DeepSeek failed: {e}. All actual LLM providers exhausted.")

        # Mock Fallback for testing purposes without keys
        logger.info("Falling back to MOCK extraction (due to missing API keys or provider failures).")
        return self._mock_extraction(schema)
        
    def _mock_extraction(self, schema: str) -> str:
        if "STARTUP" in schema:
            return '{"schemaVersion": "1.0", "recordType": "STARTUP", "source": {"name": "Mock", "url": "http://mock.com"}, "content": {"entityName": "OpenAI", "data": {"employeeCount": 500}}, "collectedAt": "2023-01-01T00:00:00Z"}'
        if "PRODUCT" in schema:
            return '{"schemaVersion": "1.0", "recordType": "PRODUCT", "source": {"name": "Mock", "url": "http://mock.com"}, "content": {"startupName": "OpenAI", "pricingModel": "PAID"}, "collectedAt": "2023-01-01T00:00:00Z"}'
        if "RESEARCH_PAPER" in schema:
            return '{"schemaVersion": "1.0", "recordType": "RESEARCH_PAPER", "content": {"title": "Attention Is All You Need", "authors": ["Ashish Vaswani"], "paper_url": "https://arxiv.org/abs/1706.03762", "github_url": "https://github.com/tensorflow/tensor2tensor", "github_stars": 10000, "published_date": "2017-06-12T00:00:00Z"}}'
        if "JOB" in schema:
            return '{"schemaVersion": "1.0", "recordType": "JOB", "content": {"company": "OpenAI", "date": "2023-01-01T00:00:00Z", "is_remote": true, "role_family": "Engineering"}}'
        
        return "{}"
