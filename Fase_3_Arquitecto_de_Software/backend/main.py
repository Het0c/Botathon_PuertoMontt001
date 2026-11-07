from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import IntegrityError

from .config import get_settings
from .database import create_local_schema
from .routers.api import router as api_router
from .routers.rpa import router as rpa_router


settings = get_settings()


def create_app(*, initialize_local_db: bool = False) -> FastAPI:
    if initialize_local_db and settings.is_sqlite:
        create_local_schema()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "API de planificación asistencial. Blue Prism procesa y compara archivos; "
            "esta API recibe JSON normalizado, valida, persiste, calcula y audita."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url="/api/v1/redoc",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key", "X-User-ID", "X-Role"],
    )
    app.include_router(rpa_router)
    app.include_router(api_router)
    app.mount("/app", StaticFiles(directory=Path(__file__).parents[2] / "frontend", html=True), name="frontend")

    @app.get("/health", tags=["Sistema"])
    def health() -> dict:
        return {
            "status": "ok",
            "environment": settings.app_env,
            "storage": "sqlite-local" if settings.is_sqlite else "postgresql-supabase",
            "excelProcessing": False,
        }

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError) -> JSONResponse:
        del exc
        return JSONResponse(status_code=409, content={"detail": "Conflicto de integridad; el registro ya existe o viola una regla"})

    return app


app = create_app(initialize_local_db=settings.app_env != "production")
