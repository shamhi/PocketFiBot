from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True)

    API_ID: int
    API_HASH: str

    DB_ENGINE: str = "mysql+aiomysql"
    DB_HOST: str = "127.0.0.1"
    DB_PORT: int = 3306
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    CREATE_ALL_TABLES: bool = False

    CLAIM_RETRY: int = 3
    SLEEP_BETWEEN_CLAIM: int = 180

    USE_PROXY_FROM_DB: bool = False


settings = Settings()
