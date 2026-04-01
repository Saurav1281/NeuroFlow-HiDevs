from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    POSTGRES_USER: str = "neuroflow"
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str = "neuroflow"
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432

    REDIS_PASSWORD: str
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379

    REDIS_URL: str | None = None

    def get_redis_url(self) -> str:
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/0"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"
    MLFLOW_TRACKING_URI: str = "http://mlflow:5000"
    JAEGER_HOST: str = "jaeger"
    JAEGER_PORT: int = 4317

    # Security
    CLIENT_ID: str = "neuroflow-client"
    CLIENT_SECRET: str = "neuroflow-secret"
    JWT_SECRET_KEY: str = "super-secret-key-for-testing"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    # LLM Provider API keys
    OPENAI_API_KEY: str | None = None
    ANTHROPIC_API_KEY: str | None = None
    DEFAULT_LLM_MODEL: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
