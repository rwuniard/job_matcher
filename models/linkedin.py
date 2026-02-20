from pydantic import BaseModel, Field
from typing import List, Optional

class Job(BaseModel):
    """Represent a single job listing from LinkedIn Job Alerts email."""
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    url: str


class LinkedInJobAlert(BaseModel):
    """Structured representation of a LinkedIn Job Alert email."""
    id: str
    subject: str
    sender: str = Field(alias="from")
    date: str
    snippet: str
    jobs: List[Job] = []

    class Config:
        # This is to allow the use of the alias "from" for the sender field.
        populate_by_name = True