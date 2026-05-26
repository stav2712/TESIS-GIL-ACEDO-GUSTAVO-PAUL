from pydantic import BaseModel, Field


class ResolvedTermOut(BaseModel):
    surface: str
    canonical: str
    category: str | None = None
    codes: list[str] = []
    matched_alias: str | None = None


class ResolvedValueOut(BaseModel):
    field: str
    canonical: str
    matched_alias: str | None = None


class QueryIn(BaseModel):
    nl: str = Field(min_length=1)
    conversation_id: str | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


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
    total_count: int | None = None
    display_total_count: int | None = None
    total_pages: int | None = None
    max_result_window: int | None = None
    max_result_window_exceeded: bool = False
    result_message: str | None = None
    selected_report_id: str | None = None
    nl_normalized: str | None = None
    schema_profile: str | None = None
    resolved_terms: list[ResolvedTermOut] = []
    resolved_values: list[ResolvedValueOut] = []
    translator_strategy: str | None = None
    can_view_sql: bool = True


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
    user_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    profile: str | None = None
    nl_normalized: str | None = None
    schema_profile: str | None = None
    resolved_terms: list[ResolvedTermOut] = []
    resolved_values: list[ResolvedValueOut] = []
    translator_strategy: str | None = None


class ConversationDetailOut(BaseModel):
    conversation: ConversationOut
    reports: list[ReportMetaOut]


class AuditReportOut(BaseModel):
    report_id: str
    conversation_id: str
    user_id: int
    username: str | None = None
    full_name: str | None = None
    profile: str | None = None
    nl: str
    sql: str
    timestamp: str
    latency_ms: int
    feedback: str | None = None


class AuditListOut(BaseModel):
    rows: list[AuditReportOut]
    total_count: int
    page: int
    page_size: int
    total_pages: int
