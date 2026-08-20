import pytest

import main
from app.webapp import webapp_api_router


def test_webapp_routes_are_registered():
    api_paths = {path for route in webapp_api_router.routes if (path := getattr(route, 'path', None))}
    assert '/api/me' in api_paths
    assert '/api/materials' in api_paths
    assert '/api/compare' in api_paths
    assert '/api/reminders' in api_paths
    assert '/api/pro/invoice' in api_paths

    app_paths = {path for route in main.app.routes if (path := getattr(route, 'path', None))}
    assert '/app' in app_paths
    assert '/assets/clarify-banner.webp' in app_paths


@pytest.mark.asyncio
async def test_ready_reports_webapp_build_flag():
    payload = await main.ready()
    assert 'webapp_build' in payload
