from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProductIdentity:
    normalized_name: str
    brand: str | None = None
    model: str | None = None
    gtin: str | None = None


def normalize_product_name(name: str) -> str:
    value = name.lower().replace('ё', 'е')
    value = re.sub(r'[^a-zа-я0-9]+', ' ', value, flags=re.I)
    return ' '.join(value.split())


def likely_same_product(a: ProductIdentity, b: ProductIdentity) -> bool:
    if a.gtin and b.gtin:
        return a.gtin == b.gtin
    if a.brand and b.brand and a.brand.lower() != b.brand.lower():
        return False
    if a.model and b.model:
        return a.model.lower() == b.model.lower()
    return a.normalized_name == b.normalized_name
