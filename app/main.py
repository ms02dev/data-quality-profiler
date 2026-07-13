import sys
import uvicorn
from app.profiler import DataProfiler


def run_profiling():
    """
    Запускает профилирование всех таблиц и сохраняет снэпшоты в БД.
    Используется в режиме CLI и в CI.
    """
    profiler = DataProfiler()
    tables = profiler.get_tables()
    
    if not tables:
        print("Не найдено таблиц для профилирования")
        return
    
    print(f"Найдено таблиц: {len(tables)}")
    
    for table in tables:
        print(f"\n{'='*60}")
        print(f"Профилирование: {table}")
        print(f"{'='*60}")
        
        report = profiler.profile_table(table)
        profiler.save_report(table, report)
        
        print(f"  ✓ Строк: {report['row_count']:,}")
        print(f"  ✓ Дублей: {report['duplicate_row_count']:,}")
        print(f"  ✓ Использована pg_stats: {report['used_pg_stats']}")
    
    print(f"\n✅ Профилирование завершено. Снэпшоты сохранены в БД.")


def start_api():
    """
    Запускает Uvicorn-сервер с FastAPI-приложением.
    reload=True — автоперезагрузка при изменении кода (только для разработки!).
    """
    print("Запуск API-сервера на http://0.0.0.0:8000")
    print("Swagger UI: http://localhost:8000/docs")
    
    uvicorn.run(
        "app.api:app",      # путь к FastAPI-приложению: модуль.переменная
        host="0.0.0.0",     # слушать все интерфейсы (нужно для Docker)
        port=8000,          # порт
        reload=True,        # автоперезагрузка при изменении файлов
        log_level="info",   # уровень логирования
    )


if __name__ == "__main__":
    # Словарь команд: аргумент → функция
    commands = {
        "run": run_profiling,
        "api": start_api,
    }
    
    # Если аргумент не передан или неизвестен — показываем справку
    if len(sys.argv) < 2 or sys.argv[1] not in commands:
        print(f"❌ Неверная команда")
        print(f"Использование: python -m app.main [{' | '.join(commands)}]")
        print(f"  run  — запустить профилирование и сохранить снэпшоты")
        print(f"  api  — запустить HTTP-сервер с REST API")
        sys.exit(1)
    
    # Выполняем выбранную команду
    commands[sys.argv[1]]()