from __future__ import annotations

import ipaddress
from typing import Optional

from fastapi import Request

from app.core.config import settings


PRIVATE_IP_RANGES = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
)


def get_client_ip(request: Request) -> Optional[str]:


    direct_ip = request.client.host if request.client else None

    if not settings.TRUST_PROXY_HEADERS:
        return direct_ip

    # Cloudflare
    cf_connecting_ip = request.headers.get("cf-connecting-ip")
    if cf_connecting_ip and is_valid_ip(cf_connecting_ip):
        return normalize_ip(cf_connecting_ip)

    # Nginx / Load Balancer
    x_real_ip = request.headers.get("x-real-ip")
    if x_real_ip and is_valid_ip(x_real_ip):
        return normalize_ip(x_real_ip)

    x_forwarded_for = request.headers.get("x-forwarded-for")
    if x_forwarded_for:
        # Format:
        # client, proxy1, proxy2
        parts = [p.strip() for p in x_forwarded_for.split(",") if p.strip()]

        for ip in parts:
            if is_valid_ip(ip):
                return normalize_ip(ip)

    return direct_ip


def is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def normalize_ip(value: str) -> str:
    return str(ipaddress.ip_address(value))


def is_private_ip(value: str | None) -> bool:
    if not value:
        return False

    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False

    return any(ip in network for network in PRIVATE_IP_RANGES)
