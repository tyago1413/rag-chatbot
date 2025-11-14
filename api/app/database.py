"""
Gerenciador de conexões do banco de dados
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Generator
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Gerenciador de conexões PostgreSQL"""
    
    @staticmethod
    @contextmanager
    def get_connection() -> Generator:
        """Context manager para conexões do banco"""
        conn = None
        try:
            conn = psycopg2.connect(
                settings.DATABASE_URL,
                cursor_factory=RealDictCursor
            )
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Erro no banco de dados: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    @staticmethod
    def execute_query(query: str, params: tuple = None, fetch: bool = False):
        """Executa query no banco"""
        with DatabaseManager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                if fetch:
                    return cur.fetchall()
                return cur.rowcount


db = DatabaseManager()