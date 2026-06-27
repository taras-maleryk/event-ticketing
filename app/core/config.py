from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    PROJECT_NAME : str = "EventTicketingAPI"
    DATABASE_URL : str
    REDIS_URL : str
    SECRET_KEY : str
    ACCESS_TOKEN_EXPIRE_MINUTES : int = 30
    DB_ECHO: bool = True

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=True)

settings = Settings()
