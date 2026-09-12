"""Aplicação FastAPI: middlewares, ciclo de vida e arquivos estáticos.

Correções:

- **CORS restrito**: o default era `allow_origins=["*"]` combinado com `allow_credentials=True`.
  Além de ser uma combinação que a especificação do CORS rejeita, abria a API (inclusive os
  `DELETE`) para qualquer origem. Agora a lista vem da configuração e as credenciais ficam
  desligadas — este serviço não usa cookie nem sessão.
- **Documentação condicional**: `/docs`, `/redoc` e `/openapi.json` só são expostos quando
  `EXPOSE_DOCS=true` (ou `DEBUG=true`).
- **README honesto**: `UPLOAD_DIR` era criado e nunca escrito — os arquivos são processados em
  memória, então a configuração foi removida do fluxo em vez de mentir sobre ela.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

setup_logging(debug=settings.DEBUG)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ciclo de vida: valida configuração crítica no start e avisa cedo sobre riscos."""
    logger.info("Iniciando %s v%s...", settings.API_TITLE, settings.API_VERSION)
    settings.ensure_directories()
    logger.info("Diretório de dados verificado: %s", settings.CHROMA_PERSIST_DIR)

    if not settings.llm_api_key_configured():
        logger.warning(
            "Chave do provedor '%s' não configurada: /chat responderá 503 até que seja definida.",
            settings.LLM_PROVIDER,
        )
    if not settings.REQUIRE_API_KEY:
        logger.warning("REQUIRE_API_KEY=false: a API está SEM autenticação (uso local apenas).")
    if "*" in settings.CORS_ORIGINS:
        logger.warning("CORS_ORIGINS contém '*': qualquer site pode chamar esta API.")

    yield
    logger.info("Encerrando aplicação...")


app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs" if settings.EXPOSE_DOCS else None,
    redoc_url="/redoc" if settings.EXPOSE_DOCS else None,
    openapi_url="/openapi.json" if settings.EXPOSE_DOCS else None,
)

# CORS: apenas as origens configuradas. Sem credenciais (não há cookie/sessão neste serviço).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

app.include_router(api_router, prefix="/api/v1")

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        """Serve a interface web integrada."""
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse(
            {
                "message": f"Bem-vindo ao {settings.API_TITLE}",
                "version": settings.API_VERSION,
            }
        )

else:

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "message": f"Bem-vindo ao {settings.API_TITLE}",
            "version": settings.API_VERSION,
        }
