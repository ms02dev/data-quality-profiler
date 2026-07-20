import psycopg2
from app.config import settings


def get_connection():
    """
    Открывает и возвращает новое соединение с БД.
    Параметры берёт из переменных окружения.

    Пример использования:
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.close()
        finally:
            conn.close()
    """
    return psycopg2.connect(
        host=settings.db_host,
        port=settings.db_port,
        dbname=settings.db_name,
        user=settings.db_user,
        password=settings.db_password.get_secret_value(),
    )

