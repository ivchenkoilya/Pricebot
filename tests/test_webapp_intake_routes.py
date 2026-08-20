from app.webapp import webapp_api_router


def test_premium_workspace_routes_are_registered():
    paths = {route.path for route in webapp_api_router.routes}
    assert '/api/intake/text' in paths
    assert '/api/intake/link' in paths
    assert '/api/intake/file' in paths
    assert '/api/memory/ask' in paths
    assert '/api/profile/stats' in paths
