import asyncio
from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import sys
import os
import logging

# Ensure src is in PYTHONPATH when running via uvicorn
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GraphOne Data Intelligence Pipeline",
    description="A production-grade, fault-tolerant ingestion pipeline for AI ecosystem data.",
    version="1.0.0"
)

class TriggerResponse(BaseModel):
    message: str
    status: str

@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "GraphOne Pipeline API"}

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}

def background_pipeline_execution():
    """Runs the pipeline in an event loop for the background task."""
    logger.info("Starting background pipeline execution...")
    try:
        # Since this runs in a threadpool from FastAPI BackgroundTasks,
        # we need to create a new event loop.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_pipeline())
        logger.info("Background pipeline execution completed successfully.")
    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}")
    finally:
        loop.close()

@app.post("/trigger", response_model=TriggerResponse, tags=["Pipeline"])
async def trigger_pipeline(background_tasks: BackgroundTasks):
    """
    Triggers the data ingestion pipeline asynchronously.
    The pipeline will acquire startups, products, papers, news, and jobs,
    and generate the GraphOne_Data_Output.xlsx file.
    """
    background_tasks.add_task(background_pipeline_execution)
    return TriggerResponse(
        message="Pipeline execution triggered in the background.",
        status="processing"
    )
