import logging
from psycopg2 import sql
from app.db import get_connection

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
    # 2. Метрики по колонке
    # ------------------------------------------------------------------
    def profile_column(self, table: str, column: str, data_type: str) -> dict:
        """
        Точный скан одной колонки.
        
        КРИТИЧЕСКИ ВАЖНО: Безопасное построение SQL через sql.Identifier.
        Имена таблиц и колонок нельзя передать через %s (это для значений),
        поэтому используем sql.SQL + sql.Identifier.
        Без этого таблица с именем 'order' (зарезервированное слово)
        сломала бы запрос.
        """
        logger.debug(f"Профилирование колонки {table}.{column} (тип: {data_type})")
        
        # Безопасное формирование имён таблиц и колонок
        t = sql.Identifier(table)
        c = sql.Identifier(column)
        
        conn = get_connection()
        try:
            cur = conn.cursor()
            
            # Базовые метрики — работают для любого типа
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
            
            # Дополнительные метрики — только для числовых и дат
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
            
            logger.info(
                f"Колонка {table}.{column}: NULL={null_count} ({null_pct}%), "
                f"distinct={distinct_count}"
            )
            
            return {
                "column_name":    column,
                "data_type":      data_type,
                "null_count":     null_count,
                "null_pct":       null_pct,
                "distinct_count": distinct_count,
                "min_value":      min_value,
                "max_value":      max_value,
                "avg_value":      avg_value,
            }
        except Exception as e:
            logger.error(f"Ошибка при профилировании {table}.{column}: {e}", exc_info=True)
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # 3. Подсчёт дублей
    # ------------------------------------------------------------------
    def count_duplicates(self, table: str) -> int:
        """
        Считает лишние строки-дубли, игнорируя PK-колонки.
        
        Алгоритм:
        1. Найти PK-колонки через information_schema
        2. Остальные колонки — ключ для GROUP BY
        3. Суммируем (count - 1) для групп с count > 1
        """
        logger.debug(f"Поиск дублей в таблице {table}")
        
        conn = get_connection()
        try:
            cur = conn.cursor()
            
            # 1. Находим колонки, которые входят в Primary Key
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
            
            # 2. Все колонки таблицы
            all_cols = [c["name"] for c in self.get_columns(table)]
            
            # 3. Оставляем только те, что НЕ входят в PK
            compare_cols = [c for c in all_cols if c not in pk_cols]
            
            # Если таблица состоит только из PK (что странно, но возможно), дублей нет
            if not compare_cols:
                logger.debug(f"Таблица {table} состоит только из PK-колонок, дублей нет")
                return 0
                
            cols_sql = sql.SQL(", ").join(sql.Identifier(c) for c in compare_cols)
            
            # 4. Группируем по не-PK колонкам и считаем, сколько раз каждая группа встречается > 1 раза
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
    # 4. Профилирование таблицы целиком (Оркестратор)
    # ------------------------------------------------------------------
    def profile_table(self, table: str) -> dict:
        """
        Главный метод: собирает отчёт по таблице целиком.
        """
        logger.info(f"🚀 Начинаем профилирование таблицы: {table}")
        
        # Собираем отчёты по каждой колонке
        column_reports = [
            self.profile_column(table, col["name"], col["type"])
            for col in self.get_columns(table)
        ]
        
        # Считаем общее количество строк
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute(
                sql.SQL("SELECT COUNT(*) FROM {tbl}").format(tbl=sql.Identifier(table))
            )
            row_count = cur.fetchone()[0]
            cur.close()
        finally:
            conn.close()
        
        # Считаем дубли
        duplicate_row_count = self.count_duplicates(table)
        
        logger.info(
            f"✅ Профилирование {table} завершено. "
            f"Строк: {row_count:,}, дублей: {duplicate_row_count:,}"
        )
        
        return {
            "table_name":          table,
            "row_count":           row_count,
            "duplicate_row_count": duplicate_row_count,
            "columns":             column_reports,
        }