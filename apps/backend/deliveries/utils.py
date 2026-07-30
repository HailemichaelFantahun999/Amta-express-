import json
import logging
import urllib.parse
from decimal import Decimal
from urllib.request import urlopen, Request

from django.conf import settings

logger = logging.getLogger(__name__)


def is_coordinate(value: str) -> bool:
    val = value.strip()
    if val.startswith("{") and val.endswith("}"):
        val = val[1:-1].strip()
    parts = val.split(",")
    if len(parts) == 2:
        try:
            float(parts[0].strip())
            float(parts[1].strip())
            return True
        except ValueError:
            pass
    return False


def resolve_to_coordinate(location: str) -> str:
    if not location:
        return ""

    if is_coordinate(location):
        val = location.strip()
        if val.startswith("{") and val.endswith("}"):
            val = val[1:-1].strip()
        val = val.replace(" ", "")
        return f"{{{val}}}"
    return ""


def get_route_info(pickup: str, delivery: str):
    default_res = (Decimal("0.00"), 0)

    if not pickup or not delivery:
        return default_res

    api_key = getattr(settings, "GEBETA_API_KEY", "")
    if not api_key:
        return default_res

    origin_coord = resolve_to_coordinate(pickup)
    dest_coord = resolve_to_coordinate(delivery)

    if not origin_coord or not dest_coord:
        return default_res

    params = {
        "origin": origin_coord,
        "destination": dest_coord,
        "apiKey": api_key,
    }

    url = f"https://mapapi.gebeta.app/api/route/direction/?{urllib.parse.urlencode(params, safe='')}"

    try:
        req = Request(url, headers={"Accept": "application/json"})
        with urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            payload = json.loads(body)

            dist = payload.get("totalDistance")
            mins = payload.get("timetaken")

            if dist is None or mins is None:
                return default_res

            distance_km = Decimal(str(dist)).quantize(Decimal("0.00"))
            estimated_drive_minutes = int(float(mins))
            return distance_km, estimated_drive_minutes
    except Exception as e:
        logger.warning(
            f"Failed to get route directions for '{origin_coord}' to '{dest_coord}': {e}"
        )

    return default_res
