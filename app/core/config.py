from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "EventTicketingAPI"
    DATABASE_URL: str
    SYNC_DATABASE_URL: str
    TEST_DATABASE_URL: str | None = None
    REDIS_URL: str
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    HOLD_FOR_MINUTES: int = 15
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    ENVIRONMENT: str = "development"
    DB_ECHO: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)


settings = Settings()
