from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api import routes_config, routes_diagnostics, routes_feedback, routes_load_test, routes_scans
from app.core.config import settings
from app.db.database import Base, SessionLocal, engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="Part Master Duplication Identifier", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(routes_config.router)
app.include_router(routes_scans.router)
app.include_router(routes_feedback.router)
app.include_router(routes_diagnostics.router)
app.include_router(routes_load_test.router)


@app.get("/health")
def health():
    return {"status": "healthy", "service": settings.service_name, "model_version": settings.model_version}


@app.get("/ready")
def ready():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": "connected", "model": "loaded"}
    finally:
        db.close()
