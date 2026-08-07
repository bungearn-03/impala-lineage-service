from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import connections, diagrams, lineage, metadata, scans
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)
settings = get_settings()

app = FastAPI(title=settings.app_name, version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

API_PREFIX = "/api/v1"
app.include_router(connections.router, prefix=API_PREFIX)
app.include_router(metadata.router, prefix=API_PREFIX)
app.include_router(scans.router, prefix=API_PREFIX)
app.include_router(lineage.router, prefix=API_PREFIX)
app.include_router(diagrams.router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", tags=["health"])
def health() -> dict:
    return {"status": "ok"}


@app.on_event("startup")
def on_startup() -> None:
    logger.info("%s starting up (environment=%s)", settings.app_name, settings.environment)
