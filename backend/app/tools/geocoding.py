import httpx2

from .exceptions import GeocodingError
from .models import GeocodingLocation

_BASE_URL = "https://geocoding-api.open-meteo.com/v1/search"
_TIMEOUT = 10.0


async def geocode_location(
    query: str,
    *,
    _transport: httpx2.AsyncBaseTransport | None = None,
) -> GeocodingLocation:
    """Resolve a human-readable location string to coordinates.

    Returns the best-matching result from Open-Meteo's geocoding service.
    Raises GeocodingError for blank queries, no matches, and all
    provider/network failures.
    """
    if not query or not query.strip():
        raise GeocodingError("Query must not be empty")

    params = {
        "name": query.strip(),
        "count": 1,
        "language": "en",
        "format": "json",
    }

    client_kwargs: dict = {"timeout": _TIMEOUT}
    if _transport is not None:
        client_kwargs["transport"] = _transport

    try:
        async with httpx2.AsyncClient(**client_kwargs) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
    except httpx2.TimeoutException as e:
        raise GeocodingError("Geocoding service request timed out") from e
    except httpx2.HTTPStatusError as e:
        raise GeocodingError(
            f"Geocoding service returned HTTP {e.response.status_code}"
        ) from e
    except httpx2.NetworkError as e:
        raise GeocodingError("Network error reaching geocoding service") from e
    except httpx2.RequestError as e:
        raise GeocodingError(f"Request to geocoding service failed: {e}") from e

    return _parse_result(response.json(), query)


def _parse_result(data: dict, query: str) -> GeocodingLocation:
    try:
        # Open-Meteo returns {} (no "results" key) when nothing matches.
        results = data.get("results", [])
        if not results:
            raise GeocodingError(f"No location found for query: {query!r}")
        first = results[0]
        return GeocodingLocation(
            name=first["name"],
            latitude=first["latitude"],
            longitude=first["longitude"],
            country=first.get("country", ""),
            country_code=first.get("country_code"),
            admin1=first.get("admin1"),
            timezone=first.get("timezone"),
        )
    except GeocodingError:
        raise
    except (KeyError, TypeError, ValueError) as e:
        raise GeocodingError(f"Unexpected geocoding response format: {e}") from e
