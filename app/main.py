from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.admin.routes import router as admin_router
from app.config import settings
from app.routers import api_router

app = FastAPI(title=settings.app_name)
app.include_router(api_router)
app.include_router(admin_router)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
