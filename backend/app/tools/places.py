import httpx2

from ..config import settings
from .exceptions import PlacesError
from .models import Place

_BASE_URL = "https://places.googleapis.com/v1/places:searchText"
_TIMEOUT = 10.0
_FIELD_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.rating,"
    "places.priceLevel,"
    "places.types,"
    "places.primaryType,"
    "places.regularOpeningHours"
)
_MAX_RESULT_LIMIT = 20

_PRICE_LEVEL_MAP: dict[str, str] = {
    "PRICE_LEVEL_FREE": "free",
    "PRICE_LEVEL_INEXPENSIVE": "inexpensive",
    "PRICE_LEVEL_MODERATE": "moderate",
    "PRICE_LEVEL_EXPENSIVE": "expensive",
    "PRICE_LEVEL_VERY_EXPENSIVE": "very_expensive",
}


async def search_places(
    query: str,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_meters: float = 5000.0,
    max_results: int = 10,
    *,
    _transport: httpx2.AsyncBaseTransport | None = None,
) -> list[Place]:
    """Search for places using the Google Places API (Text Search).

    Optionally biases results toward a geographic location when latitude and
    longitude are both provided.  Raises PlacesError for invalid inputs and
    all provider/network failures.
    """
    if latitude is not None and not (-90 <= latitude <= 90):
        raise PlacesError(f"Invalid latitude: {latitude}")
    if longitude is not None and not (-180 <= longitude <= 180):
        raise PlacesError(f"Invalid longitude: {longitude}")
    if (latitude is None) != (longitude is None):
        raise PlacesError("latitude and longitude must both be provided or both omitted")
    if not settings.google_api_key:
        raise PlacesError("Google API key is not configured (set GOOGLE_API_KEY)")

    body: dict = {
        "textQuery": query,
        "maxResultCount": max(1, min(max_results, _MAX_RESULT_LIMIT)),
    }
    if latitude is not None and longitude is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_meters,
            }
        }

    headers = {
        "X-Goog-Api-Key": settings.google_api_key,
        "X-Goog-FieldMask": _FIELD_MASK,
    }

    client_kwargs: dict = {"timeout": _TIMEOUT}
    if _transport is not None:
        client_kwargs["transport"] = _transport

    try:
        async with httpx2.AsyncClient(**client_kwargs) as client:
            response = await client.post(_BASE_URL, json=body, headers=headers)
            response.raise_for_status()
    except httpx2.TimeoutException as e:
        raise PlacesError("Places service request timed out") from e
    except httpx2.HTTPStatusError as e:
        raise PlacesError(
            f"Places service returned HTTP {e.response.status_code}"
        ) from e
    except httpx2.NetworkError as e:
        raise PlacesError("Network error reaching places service") from e
    except httpx2.RequestError as e:
        raise PlacesError(f"Request to places service failed: {e}") from e

    try:
        raw_places = response.json().get("places", [])
        return [_parse_place(p) for p in raw_places]
    except (KeyError, TypeError, ValueError) as e:
        raise PlacesError(f"Unexpected places response format: {e}") from e


def _parse_place(raw: dict) -> Place:
    location = raw.get("location", {})
    opening = raw.get("regularOpeningHours", {})
    price_raw = raw.get("priceLevel", "")
    return Place(
        place_id=raw["id"],
        name=raw.get("displayName", {}).get("text", ""),
        address=raw.get("formattedAddress", ""),
        latitude=location.get("latitude", 0.0),
        longitude=location.get("longitude", 0.0),
        rating=raw.get("rating"),
        price_level=_PRICE_LEVEL_MAP.get(price_raw),
        types=raw.get("types", []),
        primary_type=raw.get("primaryType"),
        weekday_descriptions=opening.get("weekdayDescriptions", []),
    )
