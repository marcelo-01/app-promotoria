import logging
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from app.auth.routes import router as auth_router
from app.core.config import settings
from app.customers.routes import router as customers_router
from app.merchandising.routes import router as merchandising_router
from app.products.routes import router as products_router
from app.users.routes import router as users_router
from app.infrastructure.persistence import models  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Coleta de Estoque API",
    description="App de coleta de estoque em ponto de venda — promotores",
    version="0.1.0",
)

# Aceita localhost, 127.x.x.x e IPs de rede local (essencial para testar no celular)
_DEV_ORIGIN_RE = re.compile(
    r"^https?://(localhost|127\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)(:\d+)?$"
)

_PROD_ORIGINS = [settings.frontend_url]

_CORS_HEADERS = {
    "Access-Control-Allow-Credentials": "true",
    "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
    "Access-Control-Allow-Headers": "*",
    # Necessário para o navegador ler o nome do arquivo .xlsx no download
    "Access-Control-Expose-Headers": "*",
    "Access-Control-Max-Age": "600",
}


@app.middleware("http")
async def cors_middleware(request: Request, call_next):
    origin = request.headers.get("origin", "")
    is_dev = settings.api_env != "production"

    allowed = (
        (is_dev and bool(_DEV_ORIGIN_RE.match(origin)))
        or origin in _PROD_ORIGINS
    )

    if request.method == "OPTIONS" and allowed:
        return Response(
            status_code=204,
            headers={**_CORS_HEADERS, "Access-Control-Allow-Origin": origin},
        )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": "Erro interno do servidor"})

    if allowed:
        response.headers["Access-Control-Allow-Origin"] = origin
        for key, value in _CORS_HEADERS.items():
            response.headers[key] = value

    return response


@app.get("/health")
async def health():
    return {"status": "ok", "environment": settings.api_env}


app.include_router(auth_router)
app.include_router(customers_router)
app.include_router(products_router)
app.include_router(users_router)
app.include_router(merchandising_router)
