from app.webapp.intake import router as intake_router
from app.webapp.memory import router as memory_router


def _paths(router):
    return {path for route in router.routes if (path := getattr(route, 'path', None))}


def test_premium_workspace_routes_are_registered():
    intake_paths = _paths(intake_router)
    memory_paths = _paths(memory_router)
    assert '/api/intake/text' in intake_paths
    assert '/api/intake/link' in intake_paths
    assert '/api/intake/file' in intake_paths
    assert '/api/profile/stats' in intake_paths
    assert '/api/memory/ask' in memory_paths
