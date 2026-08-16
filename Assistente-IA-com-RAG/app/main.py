from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.core.config import settings
from app.core.logging import get_logger, setup_logging

# Configura logs
setup_logging(debug=settings.DEBUG)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerenciador de ciclo de vida da aplicação (startup e shutdown)."""
    logger.info(f"Iniciando {settings.API_TITLE} v{settings.API_VERSION}...")
    settings.ensure_directories()
    logger.info(f"Diretórios de dados verificados: {settings.CHROMA_PERSIST_DIR}, {settings.UPLOAD_DIR}")
    yield
    logger.info("Encerrando aplicação...")


# Instância principal FastAPI
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    description=settings.API_DESCRIPTION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclusão das rotas da API v1
app.include_router(api_router, prefix="/api/v1")

# Configuração de arquivos estáticos para a interface Web integrada
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", include_in_schema=False)
    async def serve_index():
        """Serve a interface gráfica web para interação com o RAG."""
        index_path = static_dir / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse(
            {
                "message": f"Bem-vindo ao {settings.API_TITLE}",
                "docs": "/docs",
                "version": settings.API_VERSION,
            }
        )
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "message": f"Bem-vindo ao {settings.API_TITLE}",
            "docs": "/docs",
            "version": settings.API_VERSION,
        }
