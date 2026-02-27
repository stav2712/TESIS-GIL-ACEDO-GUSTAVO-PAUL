from pydantic import BaseModel, Field

class QueryIn(BaseModel):
    nl: str = Field(min_length=1)
    conversation_id: str | None = None
    page: int = 1
    page_size: int = 50

class QueryOut(BaseModel):
    conversation_id: str
    report_id: str
    sql: str
    timestamp: str
    latency_ms: int
    columns: list[str]
    rows: list[dict]
    page: int
    page_size: int
    row_count: int
    selected_report_id: str | None = None

class FeedbackIn(BaseModel):
    value: str  # "up" | "down"

class ConversationCreateIn(BaseModel):
    title: str | None = None

class ConversationRenameIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)

class ConversationSelectIn(BaseModel):
    report_id: str

class ConversationOut(BaseModel):
    conversation_id: str
    title: str
    created_at: str
    updated_at: str
    deleted: bool = False
    selected_report_id: str | None = None
    last_preview: str | None = None

class ReportMetaOut(BaseModel):
    report_id: str
    conversation_id: str
    nl: str
    sql: str
    timestamp: str
    latency_ms: int
    feedback: str | None = None

class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    reports: list[ReportMetaOut]