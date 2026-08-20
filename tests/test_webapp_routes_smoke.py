import pytest

import main


def test_webapp_routes_are_registered():
    paths = {path for route in main.app.routes if (path := getattr(route, 'path', None))}
    assert '/api/me' in paths
    assert '/api/materials' in paths
    assert '/api/compare' in paths
    assert '/api/reminders' in paths
    assert '/api/pro/invoice' in paths
    assert '/assets/clarify-banner.webp' in paths


@pytest.mark.asyncio
async def test_ready_reports_webapp_build_flag():
    payload = await main.ready()
    assert 'webapp_build' in payload
