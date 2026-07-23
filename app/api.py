from fastapi import FastAPI, HTTPException, Query
from app.profiler import DataProfiler  # ← Импорт сверху (не в функции!)
from app.models import TableReport, ColumnReport
from app.db import get_connection
from contextlib import asynccontextmanager
from datetime import datetime
from app.scheduler import scheduler, start_scheduler, shutdown_scheduler, TABLE_SCHEDULES, profile_one_table


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(title="Data Quality Profiler", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/latest_report", response_model=TableReport)
def get_latest_report(table: str = Query(..., description="Имя таблицы")):
    """Самый свежий снэпшот для указанной таблицы."""
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
                detail=f"Отчёт для таблицы '{table}' не найден. "
                       f"Сначала запустите профилирование: python -m app.main run"
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
    """История снэпшотов — для отслеживания тренда деградации."""
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
            {
                "snapshot_date":       str(r[0]),
                "row_count":           r[1],
                "duplicate_row_count": r[2],
            }
            for r in rows
        ],
    }


@app.get("/api/degradation")
def get_degradation(
    table: str = Query(..., description="Имя таблицы для проверки на деградацию")
):
    """
    Сравнивает два последних снэпшота и ищет колонки, 
    где процент NULL вырос более чем на 5%.
    """
    # Используем DataProfiler, а не пишем SQL здесь (Separation of Concerns)
    profiler = DataProfiler()
    result = profiler.compare_with_previous(table)
    
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Нужно минимум 2 снэпшота для таблицы '{table}', чтобы сравнить их. "
                   f"Запустите профилирование дважды."
        )
    return result


@app.get("/api/schedule/status")
def schedule_status():
    result = []
    
    for job in scheduler.get_jobs():
        # Получаем имя таблицы
        if job.args:
            table_name = job.args[0]
        else:
            table_name = None
        
        # Получаем интервал в часах
        if job.args:
            schedule_config = TABLE_SCHEDULES.get(job.args[0], {})
            interval_hours = schedule_config.get("hours")
        else:
            interval_hours = None
        
        # Получаем время следующего запуска
        if job.next_run_time is not None:
            next_run = job.next_run_time.isoformat()
        else:
            next_run = None
        
        # Собираем словарь для этой задачи
        job_info = {
            "table": table_name,
            "interval_hours": interval_hours,
            "next_run_time": next_run,
        }
        result.append(job_info)
    
    return result


@app.post("/api/schedule/trigger")
def schedule_trigger(table: str = Query(..., description="Имя таблицы для запуска вне расписания")):
    profiler = DataProfiler()
    available_tables = profiler.get_tables()
    if table not in available_tables:
        raise HTTPException(
            status_code=404,
            detail=f"Таблица '{table}' не найдена в БД. Доступные таблицы: {', '.join(available_tables)}",
        )
    scheduler.add_job(
        profile_one_table,
        trigger="date",
        run_date=datetime.now(),
        args=[table],
        id=f"manual_{table}_{datetime.now().timestamp()}",
    )
    return {"status": "triggered", "table": table}