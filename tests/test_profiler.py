import app.profiler as profiler_module
from app.profiler import DataProfiler

def test_null_count_numeric(test_table):
    """Проверяем точный подсчет NULL для числовой колонки."""
    p = DataProfiler()
    cols = {c["name"]: c["type"] for c in p.get_columns(test_table)}
    
    r = p.profile_column(test_table, "value", cols["value"])
    
    assert r["null_count"] == 1
    assert r["null_pct"] == 20.0  # 1 из 5 строк

def test_distinct_count(test_table):
    """Проверяем подсчет уникальных значений (NULL не считается уникальным)."""
    p = DataProfiler()
    cols = {c["name"]: c["type"] for c in p.get_columns(test_table)}
    
    r = p.profile_column(test_table, "value", cols["value"])
    assert r["distinct_count"] == 3  # 10.5, 30.0, 50.0

def test_duplicate_rows(test_table):
    """Проверяем поиск дублей."""
    p = DataProfiler()
    # Строка (10.5, 'a') встречается 2 раза. Лишняя - 1.
    assert p.count_duplicates(test_table) == 1

def test_pg_stats_branch(test_table, monkeypatch):
    """
    Проверяем, что профайлер переключается на pg_stats.
    monkeypatch позволяет на лету менять переменные модуля.
    """
    # Искусственно занижаем порог до 0, чтобы даже наша микро-таблица пошла в ветку pg_stats
    monkeypatch.setattr(profiler_module, "PROFILER_THRESHOLD", 0)
    
    p = DataProfiler()
    report = p.profile_table(test_table)
    
    assert report["used_pg_stats"] is True
    # В pg_stats нет min/max, они должны быть None
    assert report["columns"][0]["min_value"] is None

def test_save_and_reload(test_table, db_conn):
    """Проверяем, что save_report реально пишет в БД."""
    from datetime import datetime, timezone
    
    p = DataProfiler()
    report = p.profile_table(test_table)
    
    # Фиксируем время, чтобы потом найти эту запись
    ts = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    p.save_report(test_table, report, snapshot_date=ts)
    
    # Проверяем, что данные реально в базе
    cur = db_conn.cursor()
    cur.execute("""
        SELECT row_count FROM data_quality_table_report
        WHERE table_name = %s AND snapshot_date = %s
    """, (test_table, ts))
    row = cur.fetchone()
    cur.close()
    
    assert row is not None, "Отчет не сохранился в БД!"
    assert row[0] == 5, "Количество строк в отчете не совпадает"