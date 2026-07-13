from fastapi import FastAPI, HTTPException, Query
from app.models import TableReport, ColumnReport
from app.db import get_connection

app = FastAPI(title="Data Quality Profiler", version="0.1.0")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/api/latest_report", response_model=TableReport)
def get_latest_report(table: str = Query(..., description="Имя таблицы")):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT snapshot_date, row_count, duplicate_row_count
            FROM data_quality_table_report
            WHERE table_name = %s
            ORDER BY snapshot_date DESC
            LIMIT 1
        """, (table,))
        row = cur.fetchone()
        
        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Отчёт для таблицы '{table}' не найден. Сначала запустите профилирование: python -m app.main run"
            )
        snapshot_date, row_count, dup_count = row
        
        cur.execute("""
            SELECT column_name, data_type, null_count, null_pct,
                   distinct_count, min_value, max_value, avg_value
            FROM data_quality_column_report
            WHERE table_name = %s AND snapshot_date = %s
            ORDER BY column_name
        """, (table, snapshot_date))
        
        columns = [
            ColumnReport(
                column_name=r[0], data_type=r[1],
                null_count=r[2], null_pct=float(r[3]) if r[3] else None,
                distinct_count=r[4], min_value=r[5],
                max_value=r[6], avg_value=float(r[7]) if r[7] else None,
            )
            for r in cur.fetchall()
        ]
        cur.close()
    finally:
        conn.close()
        
    return TableReport(
        snapshot_date=snapshot_date,
        table_name=table,
        row_count=row_count,
        duplicate_row_count=dup_count,
        columns=columns,
    )

@app.get("/api/report/history")
def get_report_history(
    table: str = Query(...),
    limit: int = Query(10, ge=1, le=100),
):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT snapshot_date, row_count, duplicate_row_count
            FROM data_quality_table_report
            WHERE table_name = %s
            ORDER BY snapshot_date DESC
            LIMIT %s
        """, (table, limit))
        rows = cur.fetchall()
        cur.close()
    finally:
        conn.close()
        
    if not rows:
        raise HTTPException(status_code=404, detail=f"История для '{table}' не найдена")
        
    return {
        "table": table,
        "snapshots": [
            {"snapshot_date": str(r[0]), "row_count": r[1], "duplicate_row_count": r[2]}
            for r in rows
        ],
    }