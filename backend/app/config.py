from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
from typing import List


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"


def _load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        val = val.split("#", 1)[0].strip().strip('"').strip("'")
        os.environ.setdefault(key.strip(), val)


def _as_bool(val: str, default: bool = False) -> bool:
    if not val:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    app_name: str
    app_env: str
    demo_mode: bool
    timezone: str
    log_level: str
    log_format: str
    api_base_url: str
    agent_base_url: str
    cors_origins: List[str]

    database_url: str
    database_sync_url: str
    db_pool_mode: str
    db_pool_size: int
    db_max_overflow: int
    db_echo: bool

    redis_url: str
    celery_broker_url: str
    celery_result_backend: str

    vector_provider: str
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str

    search_provider: str
    elasticsearch_url: str
    elasticsearch_index: str

    embedding_provider: str
    embedding_model: str
    embedding_dim: int

    llm_provider: str
    anthropic_api_key: str
    llm_model_reasoning: str
    llm_model_fast: str
    openai_api_key: str
    openai_model: str
    llm_timeout_sec: int
    agent_max_steps: int
    agent_checkpointer: str

    storage_provider: str
    storage_root: Path
    media_base_url: str

    jwt_algorithm: str
    jwt_secret: str
    access_token_ttl_min: int
    refresh_token_ttl_days: int
    password_hasher: str
    service_account_secret: str

    rate_limit_agent: int
    rate_limit_customer: int
    rate_limit_anon: int

    payment_provider: str
    mock_payment_success_rate: float
    shipping_provider: str
    email_provider: str
    email_from: str
    sms_provider: str


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    _load_env()
    storage_rel = os.environ.get("STORAGE_ROOT", "./storage")
    storage_path = Path(storage_rel)
    if not storage_path.is_absolute():
        storage_path = (PROJECT_ROOT / storage_path).resolve()

    origins = [
        o.strip()
        for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001").split(",")
        if o.strip()
    ]

    return Settings(
        app_name=os.environ.get("APP_NAME", "Noir Atelier"),
        app_env=os.environ.get("APP_ENV", "development"),
        demo_mode=_as_bool(os.environ.get("DEMO_MODE", "true"), True),
        timezone=os.environ.get("TIMEZONE", "Asia/Kolkata"),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        log_format=os.environ.get("LOG_FORMAT", "console"),
        api_base_url=os.environ.get("API_BASE_URL", "http://localhost:8000"),
        agent_base_url=os.environ.get("AGENT_BASE_URL", "http://localhost:8001"),
        cors_origins=origins,
        database_url=os.environ.get("DATABASE_URL", "postgresql+asyncpg://noir:noir@localhost:5432/noir"),
        database_sync_url=os.environ.get("DATABASE_SYNC_URL", "postgresql+psycopg://noir:noir@localhost:5432/noir"),
        db_pool_mode=os.environ.get("DB_POOL_MODE", "queue"),
        db_pool_size=int(os.environ.get("DB_POOL_SIZE", "20")),
        db_max_overflow=int(os.environ.get("DB_MAX_OVERFLOW", "10")),
        db_echo=_as_bool(os.environ.get("DB_ECHO", "false"), False),
        redis_url=os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        celery_broker_url=os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1"),
        celery_result_backend=os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2"),
        vector_provider=os.environ.get("VECTOR_PROVIDER", "qdrant"),
        qdrant_url=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=os.environ.get("QDRANT_API_KEY", ""),
        qdrant_collection=os.environ.get("QDRANT_COLLECTION", "noir_products"),
        search_provider=os.environ.get("SEARCH_PROVIDER", "postgres"),
        elasticsearch_url=os.environ.get("ELASTICSEARCH_URL", "http://localhost:9200"),
        elasticsearch_index=os.environ.get("ELASTICSEARCH_INDEX", "noir_products"),
        embedding_provider=os.environ.get("EMBEDDING_PROVIDER", "local"),
        embedding_model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5"),
        embedding_dim=int(os.environ.get("EMBEDDING_DIM", "384")),
        llm_provider=os.environ.get("LLM_PROVIDER", "anthropic"),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        llm_model_reasoning=os.environ.get("LLM_MODEL_REASONING", "claude-opus-4-1"),
        llm_model_fast=os.environ.get("LLM_MODEL_FAST", "claude-sonnet-4-5"),
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        llm_timeout_sec=int(os.environ.get("LLM_TIMEOUT_SEC", "30")),
        agent_max_steps=int(os.environ.get("AGENT_MAX_STEPS", "6")),
        agent_checkpointer=os.environ.get("AGENT_CHECKPOINTER", "postgres"),
        storage_provider=os.environ.get("STORAGE_PROVIDER", "local"),
        storage_root=storage_path,
        media_base_url=os.environ.get("MEDIA_BASE_URL", "http://localhost:8000/media"),
        jwt_algorithm=os.environ.get("JWT_ALGORITHM", "HS256"),
        jwt_secret=os.environ.get("JWT_SECRET", "change-me-in-production"),
        access_token_ttl_min=int(os.environ.get("ACCESS_TOKEN_TTL_MIN", "30")),
        refresh_token_ttl_days=int(os.environ.get("REFRESH_TOKEN_TTL_DAYS", "14")),
        password_hasher=os.environ.get("PASSWORD_HASHER", "argon2"),
        service_account_secret=os.environ.get("SERVICE_ACCOUNT_SECRET", "change-me-service-secret"),
        rate_limit_agent=int(os.environ.get("RATE_LIMIT_AGENT", "100")),
        rate_limit_customer=int(os.environ.get("RATE_LIMIT_CUSTOMER", "60")),
        rate_limit_anon=int(os.environ.get("RATE_LIMIT_ANON", "30")),
        payment_provider=os.environ.get("PAYMENT_PROVIDER", "mock"),
        mock_payment_success_rate=float(os.environ.get("MOCK_PAYMENT_SUCCESS_RATE", "0.95")),
        shipping_provider=os.environ.get("SHIPPING_PROVIDER", "mock"),
        email_provider=os.environ.get("EMAIL_PROVIDER", "console"),
        email_from=os.environ.get("EMAIL_FROM", "care@noir.test"),
        sms_provider=os.environ.get("SMS_PROVIDER", "console"),
    )

