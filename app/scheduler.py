import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.profiler import DataProfiler

logger = logging.getLogger(__name__)

# Интервалы по таблицам. big_table — раз в сутки: она большая (10M строк),
# но за счёт pg_stats fallback профилируется быстро — раз в сутки достаточно
# для наблюдения за деградацией, чаще смысла нет.
TABLE_SCHEDULES = {
    "customers": {"hours": settings.schedule_customers_hours},
    "orders": {"hours": settings.schedule_orders_hours},
    "big_table": {"hours": settings.schedule_big_table_hours},
}

scheduler = BackgroundScheduler()


def profile_one_table(table_name: str) -> None:
    """Профилирует одну таблицу, сохраняет отчёт и проверяет деградацию.

    Логирование начала/конца и выбора pg_stats vs точный скан делает сам
    profile_table(); проверку деградации логирует сам compare_with_previous()
    (видно "⚠️ Обнаружена деградация..." в его же коде) — дублировать не нужно.
    Отправку алерта пока не добавляю: AlertSender ещё не существует, это День 3.
    """
    try:
        profiler = DataProfiler()
        report = profiler.profile_table(table_name)
        profiler.save_report(table_name, report)
        profiler.compare_with_previous(table_name)
    except Exception:
        logger.exception(f"Плановое профилирование не удалось: {table_name}")


def register_jobs() -> None:
    """Регистрирует повторяющиеся задачи.

    Первый запуск — сразу (next_run_time=datetime.now()), дальше по интервалу.
    Таблицы, которых нет в БД (например, seed ещё не накатился), пропускаются
    с предупреждением в лог, а не падением при первом фактическом запуске задачи.
    """
    profiler = DataProfiler()
    available_tables = set(profiler.get_tables())

    for table_name, interval_kwargs in TABLE_SCHEDULES.items():
        if table_name not in available_tables:
            logger.warning(
                f"Таблица '{table_name}' не найдена в БД, "
                f"пропускаю регистрацию задачи"
            )
            continue

        scheduler.add_job(
            profile_one_table,
            trigger="interval",
            args=[table_name],
            id=f"profile_{table_name}",
            replace_existing=True,
            next_run_time=datetime.now(),
            **interval_kwargs,
        )
        logger.info(
            f"Зарегистрирована задача для {table_name}: "
            f"каждые {interval_kwargs.get('hours', '?')} ч."
        )


def start_scheduler() -> None:
    register_jobs()
    scheduler.start()
    logger.info(f"Планировщик запущен, задач: {len(scheduler.get_jobs())}")


def shutdown_scheduler() -> None:
    scheduler.shutdown(wait=True)
    logger.info("Планировщик остановлен")