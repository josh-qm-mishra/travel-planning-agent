import httpx2

from ..config import settings
from .exceptions import RoutingError
from .models import Route, TravelMode

_BASE_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
_TIMEOUT = 10.0
_FIELD_MASK = (
    "routes.distanceMeters,"
    "routes.duration,"
    "routes.polyline.encodedPolyline"
)

# Maps our TravelMode enum values to Google Routes API travel mode strings.
_GOOGLE_TRAVEL_MODE: dict[TravelMode, str] = {
    TravelMode.DRIVE: "DRIVE",
    TravelMode.WALK: "WALK",
    TravelMode.BICYCLE: "BICYCLE",
    TravelMode.TRANSIT: "TRANSIT",
}


async def get_route(
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    travel_mode: TravelMode = TravelMode.DRIVE,
    *,
    _transport: httpx2.AsyncBaseTransport | None = None,
) -> Route:
    """Compute a route between two coordinates using the Google Routes API.

    Returns a Route with distance, duration, and optional encoded polyline.
    Raises RoutingError for invalid inputs and all provider/network failures.
    """
    if not (-90 <= origin_lat <= 90):
        raise RoutingError(f"Invalid origin latitude: {origin_lat}")
    if not (-180 <= origin_lng <= 180):
        raise RoutingError(f"Invalid origin longitude: {origin_lng}")
    if not (-90 <= destination_lat <= 90):
        raise RoutingError(f"Invalid destination latitude: {destination_lat}")
    if not (-180 <= destination_lng <= 180):
        raise RoutingError(f"Invalid destination longitude: {destination_lng}")
    if not settings.google_api_key:
        raise RoutingError("Google API key is not configured (set GOOGLE_API_KEY)")

    body = {
        "origin": {
            "location": {"latLng": {"latitude": origin_lat, "longitude": origin_lng}}
        },
        "destination": {
            "location": {
                "latLng": {"latitude": destination_lat, "longitude": destination_lng}
            }
        },
        "travelMode": _GOOGLE_TRAVEL_MODE[travel_mode],
        "computeAlternativeRoutes": False,
        "languageCode": "en-US",
        "units": "METRIC",
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
        raise RoutingError("Routing service request timed out") from e
    except httpx2.HTTPStatusError as e:
        raise RoutingError(
            f"Routing service returned HTTP {e.response.status_code}"
        ) from e
    except httpx2.NetworkError as e:
        raise RoutingError("Network error reaching routing service") from e
    except httpx2.RequestError as e:
        raise RoutingError(f"Request to routing service failed: {e}") from e

    return _parse_route(
        response.json(), origin_lat, origin_lng, destination_lat, destination_lng, travel_mode
    )


def _parse_route(
    data: dict,
    origin_lat: float,
    origin_lng: float,
    destination_lat: float,
    destination_lng: float,
    travel_mode: TravelMode,
) -> Route:
    try:
        routes = data.get("routes", [])
        if not routes:
            raise RoutingError("No routes returned by routing service")
        first = routes[0]
        # Google encodes duration as "<integer>s", e.g. "1234s"
        duration_str: str = first.get("duration", "0s")
        duration_seconds = int(float(duration_str.rstrip("s")))
        return Route(
            origin_lat=origin_lat,
            origin_lng=origin_lng,
            destination_lat=destination_lat,
            destination_lng=destination_lng,
            travel_mode=travel_mode,
            distance_meters=first.get("distanceMeters", 0),
            duration_seconds=duration_seconds,
            polyline=first.get("polyline", {}).get("encodedPolyline"),
        )
    except RoutingError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise RoutingError(f"Unexpected routing response format: {e}") from e
