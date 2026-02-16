from fastapi import APIRouter

from app.routers import batches, export, health, runs, topics

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(topics.router)
api_router.include_router(runs.router)
api_router.include_router(export.router)
api_router.include_router(batches.router)
