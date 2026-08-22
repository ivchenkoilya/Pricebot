from fastapi import APIRouter

from .api import router as core_router
from .copilot import router as copilot_router
from .intake import router as intake_router
from .memory import router as memory_router
from .source_media import router as source_media_router
from .support import router as support_router

webapp_api_router = APIRouter()
webapp_api_router.include_router(core_router)
webapp_api_router.include_router(intake_router)
webapp_api_router.include_router(memory_router)
webapp_api_router.include_router(copilot_router)
webapp_api_router.include_router(source_media_router)
webapp_api_router.include_router(support_router)

__all__ = ['webapp_api_router']
