from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    database_host: str = "db"
    database_port: int = 5432
    database_user: str = "estoque"
    database_password: str = "estoque"
    database_name: str = "estoque_db"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_env: str = "development"

    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    # 8h: o promotor passa o dia em campo e não pode ser deslogado no meio da rota
    access_token_expire_minutes: int = 480
    refresh_token_expire_days: int = 30

    frontend_url: str = "http://localhost:5174"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()
