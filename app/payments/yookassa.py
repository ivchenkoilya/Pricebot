from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


YOOKASSA_API = 'https://api.yookassa.ru/v3'


class YooKassaError(RuntimeError):
    pass


def _value(settings, attr: str, env_name: str, default=''):
    raw = getattr(settings, attr, None)
    if raw in (None, ''):
        raw = os.getenv(env_name, default)
    return raw


@dataclass(slots=True, frozen=True)
class YooKassaCheckout:
    payment_id: str
    confirmation_url: str
    status: str


class YooKassaClient:
    """Minimal async YooKassa client built on the project's existing httpx."""

    def __init__(self, settings):
        self.shop_id = str(_value(settings, 'yookassa_shop_id', 'YOOKASSA_SHOP_ID', '') or '').strip()
        self.secret_key = str(_value(settings, 'yookassa_secret_key', 'YOOKASSA_SECRET_KEY', '') or '').strip()
        self.vat_code = int(_value(settings, 'yookassa_vat_code', 'YOOKASSA_VAT_CODE', 0) or 0)
        self.tax_system_code = int(_value(settings, 'yookassa_tax_system_code', 'YOOKASSA_TAX_SYSTEM_CODE', 0) or 0)
        self.timeout = float(_value(settings, 'yookassa_timeout', 'YOOKASSA_TIMEOUT', 20.0) or 20.0)

    @property
    def configured(self) -> bool:
        return bool(self.shop_id and self.secret_key)

    def _auth(self) -> tuple[str, str]:
        if not self.configured:
            raise YooKassaError('ЮKassa ещё не настроена.')
        return self.shop_id, self.secret_key

    async def create_payment(
        self,
        *,
        amount_rub: int,
        description: str,
        return_url: str,
        metadata: dict[str, str],
        customer_email: str | None = None,
    ) -> YooKassaCheckout:
        amount_rub = max(1, int(amount_rub))
        payload: dict[str, Any] = {
            'amount': {'value': f'{amount_rub:.2f}', 'currency': 'RUB'},
            'capture': True,
            'confirmation': {'type': 'redirect', 'return_url': return_url},
            'description': description[:128],
            'metadata': {str(k): str(v)[:512] for k, v in metadata.items()},
        }

        # Receipt parameters are optional because YooKassa configuration differs
        # by tax status. When enabled, the merchant must choose the correct codes.
        if customer_email and self.vat_code > 0:
            receipt: dict[str, Any] = {
                'customer': {'email': customer_email},
                'items': [{
                    'description': description[:128],
                    'quantity': '1.00',
                    'amount': {'value': f'{amount_rub:.2f}', 'currency': 'RUB'},
                    'vat_code': self.vat_code,
                    'payment_mode': 'full_payment',
                    'payment_subject': 'service',
                }],
            }
            if self.tax_system_code > 0:
                receipt['tax_system_code'] = self.tax_system_code
            payload['receipt'] = receipt

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f'{YOOKASSA_API}/payments',
                auth=self._auth(),
                headers={
                    'Idempotence-Key': str(uuid.uuid4()),
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                },
                json=payload,
            )
        data = self._json_or_error(response)
        confirmation = data.get('confirmation') or {}
        url = str(confirmation.get('confirmation_url') or '')
        payment_id = str(data.get('id') or '')
        if not payment_id or not url:
            raise YooKassaError('ЮKassa не вернула ссылку на оплату.')
        return YooKassaCheckout(payment_id=payment_id, confirmation_url=url, status=str(data.get('status') or 'pending'))

    async def get_payment(self, payment_id: str) -> dict[str, Any]:
        payment_id = (payment_id or '').strip()
        if not payment_id:
            raise YooKassaError('Пустой идентификатор платежа.')
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f'{YOOKASSA_API}/payments/{payment_id}',
                auth=self._auth(),
                headers={'Accept': 'application/json'},
            )
        return self._json_or_error(response)

    @staticmethod
    def _json_or_error(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except Exception as exc:
            raise YooKassaError(f'ЮKassa вернула HTTP {response.status_code}.') from exc
        if response.is_error:
            description = data.get('description') or data.get('code') or f'HTTP {response.status_code}'
            raise YooKassaError(f'Ошибка ЮKassa: {description}')
        if not isinstance(data, dict):
            raise YooKassaError('Некорректный ответ ЮKassa.')
        return data
