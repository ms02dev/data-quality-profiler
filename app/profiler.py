import os
import logging
from datetime import datetime, timezone
from psycopg2 import sql
from dotenv import load_dotenv
from app.db import get_connection

# Загружаем переменные окружения из .env
load_dotenv()

# Порог для переключения между точным сканом и чтением из pg_stats.
# os.getenv возвращает строку, поэтому оборачиваем в int().
PROFILER_THRESHOLD = int(os.getenv("PROFILER_THRESHOLD", 100_000))

# Создаём логгер для этого модуля
logger = logging.getLogger(__name__)


class DataProfiler:
    """
    Ядро профайлера: интроспекция схемы, подсчёт метрик, поиск дублей.
    """

    # ------------------------------------------------------------------
    # 1. Интроспекция схемы (Читаем метаданные)
    # ------------------------------------------------------------------
    
    def get_tables(self) -> list[str]:
        """Список пользовательских таблиц в public, кроме таблиц самого профайлера."""
        logger.debug("Запрос списка таблиц из information_schema")
        query = """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
              AND table_name NOT LIKE 'data_quality_%'
            ORDER BY table_name
        """
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(query)
            result = [row[0] for row in cur.fetchall()]
            cur.close()
            logger.info(f"Найдено {len(result)} таблиц для профилирования")
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении списка таблиц: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def get_columns(self, table: str) -> list[dict]:
        """Колонки таблицы с типами, в порядке определения."""
        logger.debug(f"Запрос колонок для таблицы {table}")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = %s
                ORDER BY ordinal_position
            """, (table,))
            result = [{"name": row[0], "type": row[1]} for row in cur.fetchall()]
            cur.close()
            logger.debug(f"Найдено {len(result)} колонок в таблице {table}")
            return result
        except Exception as e:
            logger.error(f"Ошибка при получении колонок для {table}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 2. Быстрые методы для больших таблиц (pg_stats)
    # ------------------------------------------------------------------
    
    def _get_approx_row_count(self, table: str) -> int:
        """
        Быстрая оценка числа строк через pg_class.reltuples.
        Обновляется после ANALYZE, не требует полного скана.
        """
        logger.debug(f"Оценка количества строк в {table} через pg_class.reltuples")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT reltuples::bigint
                FROM pg_class
                WHERE relname = %s
                  AND relnamespace = 'public'::regnamespace
            """, (table,))
            result = cur.fetchone()
            cur.close()
            
            # Защита от None или отрицательных значений (если ANALYZE не запускался)
            estimated = result[0] if result and result[0] > 0 else 0
            logger.debug(f"Оценка для {table}: ~{estimated:,} строк")
            return estimated
        except Exception as e:
            logger.error(f"Ошибка при оценке строк в {table}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    def _profile_column_from_pg_stats(self, table: str, column: str, data_type: str) -> dict:
        """
        Читает null_frac и n_distinct из pg_stats.
        """
        logger.debug(f"Чтение статистики pg_stats для {table}.{column}")
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT null_frac, n_distinct
                FROM pg_stats
                WHERE schemaname = 'public'
                  AND tablename  = %s
                  AND attname    = %s
            """, (table, column))
            row = cur.fetchone()
            cur.close()
        except Exception as e:
            logger.error(f"Ошибка при чтении pg_stats для {table}.{column}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

        # Если статистики нет, возвращаем "пустышку", чтобы не сломать контракт функции
        if row is None:
            logger.warning(f"Для {table}.{column} нет статистики в pg_stats!")
            return {
                "column_name": column, "data_type": data_type,
                "null_count": None, "null_pct": None,
                "distinct_count": None, "min_value": None,
                "max_value": None, "avg_value": None,
            }

        null_frac, n_distinct = row
        reltuples = self._get_approx_row_count(table)
        
        # Переводим доли (проценты) в абсолютные числа
        null_count = round(null_frac * reltuples)
        null_pct   = round(float(null_frac) * 100, 2)
        
        # n_distinct может быть отрицательным (доля от reltuples)
        if n_distinct is None:
            distinct_count = None
        elif n_distinct >= 0:
            distinct_count = int(n_distinct)
        else:
            distinct_count = round(abs(n_distinct) * reltuples)

        logger.info(f"[pg_stats] {table}.{column}: NULL≈{null_pct}%, distinct≈{distinct_count}")
        
        return {
            "column_name":    column,
            "data_type":      data_type,
            "null_count":     null_count,
            "null_pct":       null_pct,
            "distinct_count": distinct_count,
            "min_value":      None,  # pg_stats не хранит min/max/avg напрямую
            "max_value":      None,
            "avg_value":      None,
        }

    # ------------------------------------------------------------------
    # 3. Метрики по колонке (с развилкой)
    # ------------------------------------------------------------------
    
    def profile_column(self, table: str, column: str, data_type: str, use_stats: bool = False) -> dict:
        """
        Профилирование одной колонки.
        Если use_stats=True — читаем из pg_stats (быстро, но приблизительно).
        Если use_stats=False — делаем точный скан (медленно, но точно).
        """
        # Ранний выход: если нужен быстрый метод, сразу возвращаем результат
        if use_stats:
            return self._profile_column_from_pg_stats(table, column, data_type)
        
        # Точный скан (работает для всех типов данных)
        logger.debug(f"Профилирование колонки {table}.{column} (тип: {data_type})")
        t = sql.Identifier(table)
        c = sql.Identifier(column)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                sql.SQL("""
                    SELECT
                        COUNT(*) FILTER (WHERE {col} IS NULL) AS null_count,
                        COUNT(*)                               AS total_count,
                        COUNT(DISTINCT {col})                  AS distinct_count
                    FROM {tbl}
                """).format(tbl=t, col=c)
            )
            null_count, total_count, distinct_count = cur.fetchone()
            null_pct = round(null_count / total_count * 100, 2) if total_count > 0 else 0.0
            
            numeric_types = {"integer", "bigint", "smallint", "numeric", "real", "double precision"}
            date_types = {"timestamp without time zone", "timestamp with time zone", "date"}
            min_value = max_value = avg_value = None
            
            if data_type in numeric_types:
                cur.execute(
                    sql.SQL("""
                        SELECT MIN({col})::text, MAX({col})::text, AVG({col})
                        FROM {tbl}
                    """).format(tbl=t, col=c)
                )
                min_value, max_value, avg_value = cur.fetchone()
                if avg_value is not None:
                    avg_value = round(float(avg_value), 4)
            elif data_type in date_types:
                cur.execute(
                    sql.SQL("""
                        SELECT MIN({col})::text, MAX({col})::text
                        FROM {tbl}
                    """).format(tbl=t, col=c)
                )
                min_value, max_value = cur.fetchone()
            cur.close()
            logger.info(f"Колонка {table}.{column}: NULL={null_count} ({null_pct}%), distinct={distinct_count}")
            return {
                "column_name": column, "data_type": data_type,
                "null_count": null_count, "null_pct": null_pct,
                "distinct_count": distinct_count,
                "min_value": min_value, "max_value": max_value, "avg_value": avg_value,
            }
        except Exception as e:
            logger.error(f"Ошибка при профилировании {table}.{column}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 4. Подсчёт дублей
    # ------------------------------------------------------------------
    
    def count_duplicates(self, table: str) -> int:
        """
        Считает лишние строки-дубли, игнорируя PK-колонки.
        """
        logger.debug(f"Поиск дублей в таблице {table}")
        conn = get_connection()
        try:
            cur = conn.cursor()
            # Находим колонки, которые входят в Primary Key
            cur.execute("""
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                   AND tc.table_schema   = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema    = 'public'
                  AND tc.table_name      = %s
            """, (table,))
            pk_cols = {row[0] for row in cur.fetchall()}
            
            # Все колонки таблицы
            all_cols = [c["name"] for c in self.get_columns(table)]
            
            # Оставляем только те, что НЕ входят в PK
            compare_cols = [c for c in all_cols if c not in pk_cols]
            if not compare_cols:
                logger.debug(f"Таблица {table} состоит только из PK-колонок, дублей нет")
                return 0
            
            cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in compare_cols)
            
            # Группируем по не-PK колонкам и считаем, сколько раз каждая группа встречается > 1 раза
            cur.execute(
                sql.SQL("""
                    SELECT COALESCE(SUM(cnt - 1), 0)
                    FROM (
                        SELECT COUNT(*) AS cnt
                        FROM {tbl}
                        GROUP BY {cols}
                        HAVING COUNT(*) > 1
                    ) sub
                """).format(tbl=sql.Identifier(table), cols=cols_sql)
            )
            result = cur.fetchone()[0] or 0
            cur.close()
            logger.info(f"Найдено {result} дублей в таблице {table}")
            return int(result)
        except Exception as e:
            logger.error(f"Ошибка при подсчёте дублей в {table}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 5. Профилирование таблицы целиком (Оркестратор)
    # ------------------------------------------------------------------
    
    def profile_table(self, table: str) -> dict:
        """
        Главный метод: собирает отчёт по таблице целиком.
        Автоматически выбирает метод (точный скан или pg_stats) в зависимости от размера таблицы.
        """
        logger.info(f"🚀 Начинаем профилирование таблицы: {table}")
        
        # Оцениваем размер таблицы
        estimated = self._get_approx_row_count(table)
        use_stats = estimated > PROFILER_THRESHOLD
        
        if use_stats:
            logger.info(f"{table}: ~{estimated:,} строк > {PROFILER_THRESHOLD}. Используем pg_stats (быстро)")
        else:
            logger.info(f"{table}: ~{estimated:,} строк <= {PROFILER_THRESHOLD}. Точный скан (медленно, но точно)")

        # Собираем отчёты по каждой колонке (передаём флаг use_stats)
        columns = self.get_columns(table)
        column_reports = [
            self.profile_column(table, col["name"], col["type"], use_stats)
            for col in columns
        ]

        # row_count — всегда точный COUNT(*)
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {tbl}").format(tbl=sql.Identifier(table)))
            row_count = cur.fetchone()[0]
            cur.close()
        except Exception as e:
            logger.error(f"Ошибка при подсчёте строк в {table}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

        # Дубли для больших таблиц пропускаем — слишком дорого (GROUP BY по всем колонкам)
        dup_count = 0 if use_stats else self.count_duplicates(table)

        logger.info(f"✅ Профилирование {table} завершено. Строк: {row_count:,}, дублей: {dup_count:,}")

        return {
            "table_name":          table,
            "row_count":           row_count,
            "duplicate_row_count": dup_count,
            "used_pg_stats":       use_stats,
            "columns":             column_reports,
        }

    # ------------------------------------------------------------------
    # 6. Сохранение отчёта в БД (Персистентность)
    # ------------------------------------------------------------------
    
    def save_report(self, table: str, report: dict, snapshot_date: datetime | None = None) -> None:
        """Сохраняет снэпшот в обе таблицы отчётов."""
        # В Python 3.12+ datetime.utcnow() устарел. Используем timezone-aware объект.
        if snapshot_date is None:
            snapshot_date = datetime.now(timezone.utc)
            
        logger.debug(f"Сохранение отчёта для {table} (дата: {snapshot_date})")
        conn = get_connection()
        try:
            cur = conn.cursor()
            
            # 1. Сохраняем метаданные таблицы
            cur.execute("""
                INSERT INTO data_quality_table_report
                    (snapshot_date, table_name, row_count, duplicate_row_count)
                VALUES (%s, %s, %s, %s)
            """, (snapshot_date, report["table_name"],
                  report["row_count"], report["duplicate_row_count"]))
            
            # 2. Сохраняем метаданные колонок
            for col in report["columns"]:
                cur.execute("""
                    INSERT INTO data_quality_column_report
                        (snapshot_date, table_name, column_name, data_type,
                         null_count, null_pct, distinct_count,
                         min_value, max_value, avg_value)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    snapshot_date, report["table_name"], col["column_name"], col["data_type"],
                    col["null_count"], col["null_pct"], col["distinct_count"],
                    col["min_value"], col["max_value"], col["avg_value"],
                ))
            
            conn.commit()  # Фиксируем транзакцию! Без этого INSERT'ы откатятся.
            cur.close()
            logger.info(f"💾 Снэпшот для {table} успешно сохранён в БД")
        except Exception as e:
            logger.error(f"Ошибка при сохранении отчёта для {table}: {e}", exc_info=True)
            conn.rollback()  # Откатываем транзакцию при ошибке, чтобы не оставить "мусор"
            raise
        finally:
            conn.close()