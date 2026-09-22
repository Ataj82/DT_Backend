from __future__ import annotations

from typing import Optional

from fastapi import Request
from user_agents import parse

from app.features.auth.device.geoip import lookup_location
from app.features.auth.device.ip import get_client_ip
from app.features.auth.device.schemas import DeviceInfo


def detect_device_from_request(request: Request) -> DeviceInfo:
    user_agent = request.headers.get("user-agent")
    ip_address = get_client_ip(request)

    return detect_device(
        user_agent=user_agent,
        ip_address=ip_address,
    )


def detect_device(
    user_agent: Optional[str],
    ip_address: Optional[str] = None,
) -> DeviceInfo:
    if not user_agent:
        location = lookup_location(ip_address)

        return DeviceInfo(
            device_name="Unknown Device",
            device_type="unknown",
            device_brand=None,
            device_model=None,
            os_name="Unknown",
            os_version=None,
            browser_name="Unknown",
            browser_version=None,
            is_mobile=False,
            is_tablet=False,
            is_pc=False,
            is_bot=False,
            is_touch_capable=False,
            ip_address=ip_address,
            user_agent=user_agent,
            location=location,
        )

    ua = parse(user_agent)

    os_name = normalize_name(ua.os.family)
    os_version = normalize_version(ua.os.version_string)

    browser_name = normalize_name(ua.browser.family)
    browser_version = normalize_version(ua.browser.version_string)

    device_brand = normalize_optional(ua.device.brand)
    device_model = normalize_optional(ua.device.model)

    device_type = get_device_type(ua)
    is_touch_capable = ua.is_mobile or ua.is_tablet

    device_name = build_device_name(
        browser_name=browser_name,
        os_name=os_name,
        device_brand=device_brand,
        device_model=device_model,
        device_type=device_type,
        is_bot=ua.is_bot,
    )

    location = lookup_location(ip_address)

    return DeviceInfo(
        device_name=device_name,

        device_type=device_type,
        device_brand=device_brand,
        device_model=device_model,

        os_name=os_name,
        os_version=os_version,

        browser_name=browser_name,
        browser_version=browser_version,

        is_mobile=ua.is_mobile,
        is_tablet=ua.is_tablet,
        is_pc=ua.is_pc,
        is_bot=ua.is_bot,
        is_touch_capable=is_touch_capable,

        ip_address=ip_address,
        user_agent=user_agent,

        location=location,
    )


def get_device_type(ua) -> str:
    if ua.is_bot:
        return "bot"

    if ua.is_tablet:
        return "tablet"

    if ua.is_mobile:
        return "mobile"

    if ua.is_pc:
        return "desktop"

    return "unknown"


def build_device_name(
    *,
    browser_name: str,
    os_name: str,
    device_brand: Optional[str],
    device_model: Optional[str],
    device_type: str,
    is_bot: bool,
) -> str:
    if is_bot:
        if browser_name != "Unknown":
            return f"{browser_name} Bot"
        return "Bot"

    # Format mobile/tablet brand and model if available (e.g. iPhone Safari, Samsung SM-S918B Chrome)
    brand_model = join_non_empty([device_brand, device_model])

    if brand_model:
        if browser_name != "Unknown":
            return f"{brand_model} · {browser_name}"
        return brand_model

    if browser_name != "Unknown" and os_name != "Unknown":
        return f"{browser_name} on {os_name}"

    if os_name != "Unknown":
        if device_type == "mobile":
            return f"Mobile Device on {os_name}"

        if device_type == "tablet":
            return f"Tablet on {os_name}"

        if device_type == "desktop":
            return f"Desktop on {os_name}"

        return os_name

    if browser_name != "Unknown":
        return browser_name

    return "Unknown Device"


def normalize_name(value: Optional[str]) -> str:
    if not value:
        return "Unknown"

    value = value.strip()

    if not value:
        return "Unknown"

    mapping = {
        "Mac OS X": "macOS",
        "iOS": "iOS",
        "Android": "Android",
        "Windows": "Windows",
        "Chrome": "Chrome",
        "Chrome Mobile": "Chrome",
        "Mobile Safari": "Safari",
        "Firefox Mobile": "Firefox",
        "Edge": "Edge",
        "Edge Mobile": "Edge",
        "IE": "Internet Explorer",
    }

    return mapping.get(value, value)


def normalize_version(value: Optional[str]) -> Optional[str]:
    value = normalize_optional(value)

    if not value:
        return None

    return value


def normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None

    value = str(value).strip()

    if not value:
        return None

    if value.lower() in {"none", "unknown", "other"}:
        return None

    return value


def join_non_empty(items: list[Optional[str]]) -> Optional[str]:
    values = [item for item in items if item]

    if not values:
        return None

    return " ".join(values)
