from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    POSTGRES_USER: str = "neuroflow"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "neuroflow"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    
    REDIS_PASSWORD: str
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"
    JAEGER_HOST: str = "jaeger"
    JAEGER_PORT: int = 4317
    
    # LLM Provider API keys
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"
    
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
