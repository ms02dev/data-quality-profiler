import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # читает .env из папки, откуда запущен Python


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
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 5432)),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )