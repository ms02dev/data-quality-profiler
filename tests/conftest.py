import pytest
from app.db import get_connection

@pytest.fixture(scope="session")
def db_conn():
    """
    scope="session" означает, что соединение создастся ОДИН РАЗ на все тесты.
    Это в разы быстрее, чем открывать/закрывать его перед каждым тестом.
    """
    conn = get_connection()
    yield conn  # yield передает управление тестам
    conn.close() # выполнится после завершения всех тестов

@pytest.fixture
def test_table(db_conn):
    """
    Эта фикстура выполняется ПЕРЕД каждым тестом, где она запрошена.
    Она создает крошечную таблицу с ИЗВЕСТНЫМИ данными.
    """
    cur = db_conn.cursor()
    cur.execute("""
        DROP TABLE IF EXISTS _test_fixture;
        CREATE TABLE _test_fixture (
            id    integer PRIMARY KEY,
            value numeric,
            label text
        );
        -- Данные подобраны так, чтобы мы точно знали ответы:
        -- value: 1 NULL (из 5 строк = 20%), 3 уникальных (10.5, 30.0, 50.0)
        -- label: 1 NULL
        -- Дубли: строка (1, 10.5, 'a') встречается дважды -> 1 дубль
        INSERT INTO _test_fixture VALUES
            (1, 10.5, 'a'),
            (2, NULL, 'b'),
            (3, 30.0, NULL),
            (4, 10.5, 'a'), -- дубль первой строки
            (5, 50.0, 'c');
            
        -- ВАЖНО: вызываем ANALYZE, чтобы pg_stats заполнился!
        ANALYZE _test_fixture;
    """)
    db_conn.commit() # Фиксируем создание таблицы
    
    yield "_test_fixture" # Передаем имя таблицы в тест
    
    # Teardown (очистка после теста)
    cur = db_conn.cursor()
    cur.execute("DROP TABLE IF EXISTS _test_fixture;")
    db_conn.commit()
    cur.close()