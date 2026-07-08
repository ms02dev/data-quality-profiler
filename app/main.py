import sys
import logging
from app.profiler import DataProfiler

# Глобальная настройка логирования — ВЫЗЫВАЕТСЯ ОДИН РАЗ
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'  # Убираем миллисекунды для читаемости
)
logger = logging.getLogger(__name__)

def run_profiling():
    logger.info("🚀 Запуск профилирования всех таблиц")
    profiler = DataProfiler()
    tables = profiler.get_tables()
    logger.info(f"Найдено таблиц для профилирования: {len(tables)}")
    
    for table in tables:
        logger.info(f"{'='*50}")
        logger.info(f"Профилирование таблицы: {table}")
        logger.info(f"{'='*50}")
        
        report = profiler.profile_table(table)

        #НОВОЕ: Сохраняем снэпшот в БД
        profiler.save_report(table, report)
        
        logger.info(f"  ✓ Строк: {report['row_count']:,}")
        logger.info(f"  ✓ Дублей: {report['duplicate_row_count']:,}")
        logger.info(f"  ✓ Использовали pg_stats: {report['used_pg_stats']}") 
        
        for col in report["columns"]:
            logger.info(f"  Колонка '{col['column_name']}' ({col['data_type']})")
            logger.info(f"    NULL: {col['null_count']:,} ({col['null_pct']}%)")
            logger.info(f"    Уникальных: {col['distinct_count']:,}")
            if col["min_value"] is not None:
                logger.info(f"    Min/Max: {col['min_value']} / {col['max_value']}")
            if col["avg_value"] is not None:
                logger.info(f"    Avg: {col['avg_value']}")
    
# (Неделя 3): Финальный лог
    logger.info("✅ Профилирование и сохранение всех таблиц завершено")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        run_profiling()
    else:
        print("Использование: python -m app.main run")  # ← print для справки