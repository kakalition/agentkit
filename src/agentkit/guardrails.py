"""Cross-cutting safety helpers (loopback checks + exposure warnings)."""

from __future__ import annotations

import ipaddress
import sys


def is_loopback(host: str | None) -> bool:
    if host in (None, "", "localhost"):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def warn_if_exposed(host: str | None, service: str) -> None:
    """Warn when a server is bound to a non-loopback interface."""
    if not is_loopback(host):
        print(
            f"WARNING: {service} is binding {host!r}, which is reachable beyond "
            "loopback. Put it behind a reverse proxy with authentication.",
            file=sys.stderr,
        )
