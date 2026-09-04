"""
SentinelShield AI - FastAPI Application Server.

Initializes FastAPI with CORS, routes, and static file serving for the dashboard.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from packages.core.database import init_db


DASHBOARD_DIR = Path(__file__).resolve().parent.parent / "dashboard"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(
    title="SentinelShield AI",
    description="Autonomous dispute defense and evidence orchestration engine for Razorpay merchants",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from apps.api.routes.webhooks import router as webhooks_router
from apps.api.routes.disputes import router as disputes_router
from apps.api.routes.eval_routes import router as eval_router

app.include_router(webhooks_router, prefix="/api/v1")
app.include_router(disputes_router, prefix="/api/v1")
app.include_router(eval_router, prefix="/api/v1")

if DASHBOARD_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")


@app.get("/")
async def root():
    return {
        "service": "SentinelShield AI",
        "version": "0.1.0",
        "status": "running",
        "dashboard": "/dashboard",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
