from __future__ import annotations

from functools import lru_cache
from typing import Optional

import geoip2.database
import geoip2.errors

from app.features.auth.device.ip import is_private_ip
from app.features.auth.device.schemas import LocationInfo
from app.core.config import settings


@lru_cache(maxsize=1)
def get_geoip_reader():
    if not settings.ENABLE_GEOIP:
        return None

    if not settings.GEOIP_CITY_DB_PATH:
        return None

    return geoip2.database.Reader(settings.GEOIP_CITY_DB_PATH)


def lookup_location(ip_address: str | None) -> Optional[LocationInfo]:
    if not ip_address:
        return None

    if is_private_ip(ip_address):
        return None

    reader = get_geoip_reader()
    if not reader:
        return None

    try:
        response = reader.city(ip_address)

        return LocationInfo(
            country_code=response.country.iso_code,
            country_name=response.country.name,
            city_name=response.city.name,
            latitude=response.location.latitude,
            longitude=response.location.longitude,
            timezone=response.location.time_zone,
        )

    except geoip2.errors.AddressNotFoundError:
        return None
    except Exception:
        # Suppress GeoIP lookup failures to avoid blocking user authentication
        return None
