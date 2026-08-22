import pytest

import main
from app.webapp.api import router as core_router
from app.webapp.copilot import router as copilot_router
from app.webapp.memory import router as memory_router


def _paths(router):
    return {path for route in router.routes if (path := getattr(route, 'path', None))}


def test_webapp_routes_are_registered():
    core_paths = _paths(core_router)
    assert '/api/me' in core_paths
    assert '/api/materials' in core_paths
    assert '/api/compare' in core_paths
    assert '/api/reminders' in core_paths
    assert '/api/pro/invoice' in core_paths

    assert '/api/memory/ask' in _paths(memory_router)
    assert _paths(copilot_router)

    app_paths = {path for route in main.app.routes if (path := getattr(route, 'path', None))}
    assert '/app' in app_paths
    assert '/assets/clarify-banner.webp' in app_paths


@pytest.mark.asyncio
async def test_ready_reports_webapp_build_flag():
    payload = await main.ready()
    assert 'webapp_build' in payload
