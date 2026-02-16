from fastapi import FastAPI

from app.config import settings
from app.routers import api_router

app = FastAPI(title=settings.app_name)
app.include_router(api_router)
