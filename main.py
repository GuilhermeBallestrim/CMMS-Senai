"""SENAI CMMS web application entry point."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from backend.api import router as api_router
from backend.config import settings
from backend.database import db
import web.common as web_common
from web.routes_auth import router as auth_router
from web.routes_calls import router as calls_router
from web.routes_dashboard import router as dashboard_router
from web.routes_equipment import router as equipment_router
from web.routes_history import router as history_router
from web.routes_indicators import router as indicators_router
from web.routes_notifications import router as notifications_router
from web.routes_purchases import router as purchases_router
from web.routes_settings import router as settings_router
from web.routes_work_orders import router as work_orders_router

ROOT_DIR = Path(__file__).resolve().parent
FRONTEND_DIR = ROOT_DIR / "frontend"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield


app = FastAPI(title="SENAI CMMS", description="Sistema de gestão de manutenção", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    same_site="lax",
    https_only=settings.session_https_only,
    session_cookie="cmms_session",
    max_age=60 * 60 * 8,
)
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")
templates = Jinja2Templates(directory=FRONTEND_DIR / "templates")
web_common.init_templates(templates)

# Include API routes (under /api prefix)
app.include_router(api_router)

# Include web UI routes
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(calls_router)
app.include_router(equipment_router)
app.include_router(work_orders_router)
app.include_router(purchases_router)
app.include_router(settings_router)
app.include_router(history_router)
app.include_router(indicators_router)
app.include_router(notifications_router)


@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse("/dashboard", status_code=303)