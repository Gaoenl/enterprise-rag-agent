from pydantic import BaseModel, Field


class SummaryMessage(BaseModel):
    role: str
    content: str


class SummarizeRequest(BaseModel):
    messages: list[SummaryMessage] = Field(..., min_length=1)
    old_summary: str = ""


class SummarizeResponse(BaseModel):
    summary: str