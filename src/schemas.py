from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

class StartupData(BaseModel):
    employeeCount: Optional[int] = None

class StartupContent(BaseModel):
    entityName: str
    data: Optional[StartupData] = None

class StartupSource(BaseModel):
    name: str
    url: str

class StartupEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "STARTUP"
    source: StartupSource
    content: StartupContent
    collectedAt: str

class ProductContent(BaseModel):
    startupName: str
    pricingModel: Literal["FREE", "FREEMIUM", "PAID", "ENTERPRISE"]

class ProductEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "PRODUCT"
    source: StartupSource
    content: ProductContent
    collectedAt: str

class ResearchPaperContent(BaseModel):
    title: str
    authors: List[str]
    paper_url: str
    github_url: Optional[str] = None
    github_stars: Optional[int] = None
    published_date: str

class ResearchPaperEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "RESEARCH_PAPER"
    content: ResearchPaperContent

class JobContent(BaseModel):
    company: str
    date: str
    is_remote: bool
    role_family: str

class JobEntity(BaseModel):
    schemaVersion: str = "1.0"
    recordType: str = "JOB"
    content: JobContent
