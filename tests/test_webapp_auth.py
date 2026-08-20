import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.webapp.auth import validate_init_data


def signed_init_data(token: str, user_id: int = 12345, auth_date: int | None = None) -> str:
    values = {
        'auth_date': str(auth_date if auth_date is not None else int(time.time())),
        'query_id': 'AAE-test-query',
        'user': json.dumps({'id': user_id, 'first_name': 'Test', 'username': 'clarify_test'}, separators=(',', ':')),
    }
    check_string = '\n'.join(f'{key}={values[key]}' for key in sorted(values))
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    values['hash'] = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_valid_telegram_init_data():
    user = validate_init_data(signed_init_data('secret-token', 777), 'secret-token', 3600)
    assert user.id == 777
    assert user.username == 'clarify_test'


def test_invalid_telegram_init_data_hash():
    value = signed_init_data('secret-token', 777).replace('clarify_test', 'attacker')
    with pytest.raises(ValueError, match='invalid hash'):
        validate_init_data(value, 'secret-token', 3600)


def test_expired_telegram_init_data():
    old = int(time.time()) - 7200
    with pytest.raises(ValueError, match='expired'):
        validate_init_data(signed_init_data('secret-token', 777, old), 'secret-token', 3600)
