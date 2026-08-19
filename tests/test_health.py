import pytest

import main


@pytest.mark.asyncio
async def test_health_payload():
    payload = await main.health()
    assert payload == {'status': 'ok', 'app': 'RAZBERI', 'version': '0.1.0'}
