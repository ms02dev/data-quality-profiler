from datetime import datetime
from typing import Optional
from pydantic import BaseModel

class ColumnReport(BaseModel):
    column_name:   str
    data_type:     str
    null_count:    Optional[int]   = None
    null_pct:      Optional[float] = None
    distinct_count: Optional[int]  = None
    min_value:     Optional[str]   = None
    max_value:     Optional[str]   = None
    avg_value:     Optional[float] = None

class TableReport(BaseModel):
    snapshot_date:       datetime
    table_name:          str
    row_count:           int
    duplicate_row_count: int
    columns:             list[ColumnReport]