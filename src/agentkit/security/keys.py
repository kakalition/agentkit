"""API-key parsing and hashing.

Keys are never stored or logged in plaintext: config/env keys are hashed with
SHA-256 (matching the DB ``APIKey.key_hash`` column) so lookups are a dict/DB hit
on the digest.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class APIKeySpec:
    """A configured API key: the secret plus the actor it resolves to."""

    name: str
    key: str
    owner_id: str
    roles: tuple[str, ...] = ()


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def key_prefix(key: str, length: int = 8) -> str:
    return key[:length]


def _split_roles(value: Any) -> tuple[str, ...]:
    if value is None or value == "":
        return ()
    if isinstance(value, str):
        return tuple(part for part in value.replace(",", " ").split() if part)
    return tuple(str(part) for part in value)


def _spec_from_entry(name: str, value: Any) -> APIKeySpec:
    if isinstance(value, str):
        return APIKeySpec(name=name, key=value, owner_id=name)
    key = str(value.get("key", ""))
    owner = str(value.get("owner") or value.get("owner_id") or name)
    roles = _split_roles(value.get("roles"))
    return APIKeySpec(name=str(value.get("name") or name), key=key, owner_id=owner, roles=roles)


def _parse_csv(text: str) -> list[APIKeySpec]:
    specs: list[APIKeySpec] = []
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = chunk.split(":")
        name = parts[0].strip()
        key = parts[1].strip() if len(parts) > 1 else ""
        owner = parts[2].strip() if len(parts) > 2 and parts[2].strip() else name
        roles = _split_roles(" ".join(parts[3:]).replace("|", " ")) if len(parts) > 3 else ()
        specs.append(APIKeySpec(name=name, key=key, owner_id=owner, roles=roles))
    return specs


def parse_api_keys(raw: Any) -> list[APIKeySpec]:
    """Normalize ``auth_api_keys`` config into specs (JSON object or CSV)."""
    if raw is None or raw == "":
        return []
    data = raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return []  # malformed JSON config is never silently trusted
        else:
            return _parse_csv(text)
    if isinstance(data, dict):
        return [_spec_from_entry(str(name), value) for name, value in data.items()]
    if isinstance(data, list):
        return [_spec_from_entry("", value) for value in data]
    return []


__all__ = ["APIKeySpec", "hash_key", "key_prefix", "parse_api_keys"]
