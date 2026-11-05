from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .api import admin, agents, audit, auth_routes, cart, config, customers, orders, products, returns
from .config import PROJECT_ROOT, get_settings
from .database import get_active_db_backend, get_sync_engine
from .utils.exceptions import AppError

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    engine = get_sync_engine()
    if settings.demo_mode:
        from ..scripts.seed_demo import seed_database

        seed_database(engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    trace_id = getattr(request.state, "trace_id", "TRC-000000")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "details": exc.details,
            "trace_id": trace_id,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        },
    )


app.include_router(auth_routes.router, tags=["Authentication & RBAC"])
app.include_router(products.router, tags=["Products & Inventory"])
app.include_router(cart.router, tags=["Cart & Coupons"])
app.include_router(orders.router, tags=["Orders, Payments & Shipments"])
app.include_router(returns.router, tags=["Returns, Refunds & Support"])
app.include_router(customers.router, tags=["Customers & Addresses"])
app.include_router(config.router, tags=["Business Configuration"])
app.include_router(admin.router, tags=["Admin Portal"])
app.include_router(audit.router, tags=["Audit Log"])
app.include_router(agents.router, tags=["9-Agent Orchestrator"])


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {
        "status": "healthy",
        "app": settings.app_name,
        "env": settings.app_env,
        "demo_mode": settings.demo_mode,
        "db_backend": get_active_db_backend(),
        "timezone": settings.timezone,
        "storage_provider": settings.storage_provider,
        "search_provider": settings.search_provider,
        "vector_provider": settings.vector_provider,
    }


@app.get("/", tags=["System"])
async def root() -> dict:
    return {
        "message": f"Welcome to {settings.app_name} Unified AI-Native Commerce API",
        "documentation": "/docs",
        "health": "/health",
        "storefront_ui": "/storefront/",
    }


_packages_dir = PROJECT_ROOT / "frontend" / "packages"
_storefront_dir = PROJECT_ROOT / "frontend" / "apps" / "storefront"
_storage_dir = Path(settings.storage_root).resolve()
_storage_dir.mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory=str(_storage_dir)), name="media")
if _packages_dir.is_dir():
    app.mount("/packages", StaticFiles(directory=str(_packages_dir)), name="frontend_packages")
if _storefront_dir.is_dir():
    app.mount("/storefront", StaticFiles(directory=str(_storefront_dir), html=True), name="storefront_ui")
