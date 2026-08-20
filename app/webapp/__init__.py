from fastapi import APIRouter

from .api import router as core_router
from .intake import router as intake_router

webapp_api_router = APIRouter()
webapp_api_router.include_router(core_router)
webapp_api_router.include_router(intake_router)

__all__ = ['webapp_api_router']
