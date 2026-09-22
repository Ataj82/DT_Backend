from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class LocationInfo:
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    city_name: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None


@dataclass(frozen=True)
class DeviceInfo:
    device_name: str

    device_type: str
    device_brand: Optional[str]
    device_model: Optional[str]

    os_name: str
    os_version: Optional[str]

    browser_name: str
    browser_version: Optional[str]

    is_mobile: bool
    is_tablet: bool
    is_pc: bool
    is_bot: bool
    is_touch_capable: bool

    ip_address: Optional[str]
    user_agent: Optional[str]

    location: Optional[LocationInfo] = None
