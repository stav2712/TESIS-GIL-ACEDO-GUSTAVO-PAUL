from pydantic import BaseModel, Field

class QueryIn(BaseModel):
    nl: str = Field(min_length=1)
    page: int = 1
    page_size: int = 50

class QueryOut(BaseModel):
    report_id: str
    sql: str
    latency_ms: int
    columns: list[str]
    rows: list[dict]
    page: int
    page_size: int
    row_count: int

class FeedbackIn(BaseModel):
    # “útil/no útil” (pulgar arriba/abajo) :contentReference[oaicite:9]{index=9}
    value: str  # "up" | "down"