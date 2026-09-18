from pydantic_settings import BaseSettings

# Valores que o `.env.example` traz preenchidos para o ambiente de desenvolvimento
# subir com um `cp` só. Em produção eles são recusados na largada — ver
# `_assert_production_ready`.
DEV_SECRET_KEY = "dev-secret-key-change-in-production"
DEV_DATABASE_PASSWORD = "estoque"


class Settings(BaseSettings):
    database_url: str
    database_host: str = "db"
    database_port: int = 5432
    database_user: str = "estoque"
    database_password: str = DEV_DATABASE_PASSWORD
    database_name: str = "estoque_db"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_env: str = "development"

    secret_key: str = DEV_SECRET_KEY
    algorithm: str = "HS256"
    # 8h: o promotor passa o dia em campo e não pode ser deslogado no meio da rota
    access_token_expire_minutes: int = 480
    refresh_token_expire_days: int = 30

    frontend_url: str = "http://localhost:5174"

    # Fuso do usuário, não do servidor: o contêiner roda em UTC e a coluna
    # "Data da visita" da planilha é onde o administrador filtra. Sem isto, a
    # contagem das 22h sai na planilha com a data do dia seguinte.
    timezone: str = "America/Sao_Paulo"

    # Quem assina a folha do pedido que o vendedor entrega ao comprador da
    # loja. Não sai de `Tenant.name`, que é slug ("fv-laticinios") e ficaria
    # feio num documento que vai para a mão de terceiro. Vazio: a linha do
    # fornecedor simplesmente não aparece no PDF.
    company_name: str = ""

    @property
    def is_production(self) -> bool:
        return self.api_env == "production"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


def _assert_production_ready(config: Settings) -> None:
    """Recusa subir em produção com as credenciais que estão no repositório.

    Falhar aqui é ruidoso e imediato — o contêiner não sobe e o motivo está na
    primeira linha do log. A alternativa é a API subir feliz assinando JWT com
    uma chave que qualquer um que leia o `.env.example` conhece.
    """
    if not config.is_production:
        return

    problemas = []
    if config.secret_key == DEV_SECRET_KEY:
        problemas.append(
            "SECRET_KEY ainda é a do .env.example — qualquer um que leia o "
            "repositório forja um token de administrador. "
            "Gere a sua com: openssl rand -hex 32"
        )
    if config.database_password == DEV_DATABASE_PASSWORD:
        problemas.append(
            "DATABASE_PASSWORD/POSTGRES_PASSWORD ainda é a do .env.example. "
            "Gere a sua com: openssl rand -hex 16"
        )

    if problemas:
        raise RuntimeError(
            "Configuração insegura para API_ENV=production:\n  - "
            + "\n  - ".join(problemas)
        )


settings = Settings()
_assert_production_ready(settings)
