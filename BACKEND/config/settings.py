from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    APP_NAME: str = "AYO"
    APP_VERSION: str = "1.0.0"

    API_PREFIX: str = "/api"

    DEBUG: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
