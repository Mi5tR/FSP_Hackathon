import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, candidate, employer, integrations, public
from app.core.config import settings
from app.core.db import Base, engine, ensure_columns

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Для MVP схема создаётся при старте; в проде нужны миграции Alembic
    Base.metadata.create_all(engine)
    ensure_columns()
    yield


app = FastAPI(
    title="ФСП Карьера API",
    version="1.0.0",
    description=(
        "Платформа подбора ИТ-специалистов с обратной механикой: кандидаты распределяются по категориям "
        "по итогам адаптивного теста, работодатель находит категорию и сам приглашает кандидата "
        "с указанием вилки зарплаты."
    ),
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

for r in (auth.router, public.router, candidate.router, employer.router, integrations.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["public"])
def health():
    return {"status": "ok"}
