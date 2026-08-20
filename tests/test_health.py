import pytest

import main


@pytest.mark.asyncio
async def test_health_payload():
    payload = await main.health()
    assert payload == {'status': 'ok', 'app': 'Clarify', 'version': '0.5.1'}
