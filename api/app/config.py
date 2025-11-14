"""
Configurações da aplicação
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "postgresql://impar:impar123@postgres:5432/impar"
    
    # Scraping
    SCRAPE_URL: str = "https://pt.wikipedia.org/wiki/Intelig%C3%AAncia_artificial"
    
    # Embeddings
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"
    EMBEDDING_DIMENSION: int = 384
    
    # RAG
    TOP_K: int = 5
    MAX_CONTEXT_CHARS: int = 2000
    CHUNK_SIZE: int = 500
    CHUNK_OVERLAP: int = 50
    
    # LLM
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "llama3"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()