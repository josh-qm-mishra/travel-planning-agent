"""Tests for the travel tools layer (weather, places, routing).

All tests mock the HTTP boundary via httpx2.MockTransport so no live network
calls are made.
"""
from datetime import date
from unittest.mock import patch

import httpx2
import pytest

from app.config import settings
from app.tools.exceptions import GeocodingError, PlacesError, RoutingError, WeatherError
from app.tools.geocoding import geocode_location
from app.tools.models import TravelMode, WeatherCondition
from app.tools.places import search_places
from app.tools.routing import get_route
from app.tools.weather import get_weather_forecast

# ---------------------------------------------------------------------------
# Transport helpers
# ---------------------------------------------------------------------------


def json_transport(status_code: int, data: dict) -> httpx2.MockTransport:
    """MockTransport that returns a JSON response with the given status code."""
    def handler(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status_code, json=data)
    return httpx2.MockTransport(handler)


def error_transport(exc: Exception) -> httpx2.MockTransport:
    """MockTransport that raises the given exception when called."""
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise exc
    return httpx2.MockTransport(handler)


# ---------------------------------------------------------------------------
# Sample provider payloads
# ---------------------------------------------------------------------------

WEATHER_PAYLOAD = {
    "latitude": 48.8566,
    "longitude": 2.3522,
    "timezone": "Europe/Paris",
    "daily_units": {
        "time": "iso8601",
        "weather_code": "wmo code",
        "temperature_2m_max": "°C",
        "temperature_2m_min": "°C",
        "precipitation_sum": "mm",
        "precipitation_probability_max": "%",
    },
    "daily": {
        "time": ["2025-06-01", "2025-06-02"],
        "weather_code": [0, 63],
        "temperature_2m_max": [22.5, 18.0],
        "temperature_2m_min": [15.0, 12.0],
        "precipitation_sum": [0.0, 4.2],
        "precipitation_probability_max": [5, 75],
    },
}

PLACES_PAYLOAD = {
    "places": [
        {
            "id": "ChIJLU7jZClu5kcR4PcOOO6p3I0",
            "displayName": {"text": "Louvre Museum", "languageCode": "en"},
            "formattedAddress": "Rue de Rivoli, 75001 Paris, France",
            "location": {"latitude": 48.8606, "longitude": 2.3376},
            "rating": 4.7,
            "priceLevel": "PRICE_LEVEL_MODERATE",
            "types": ["museum", "tourist_attraction"],
            "primaryType": "museum",
            "regularOpeningHours": {
                "weekdayDescriptions": [
                    "Monday: Closed",
                    "Tuesday: 9:00 AM – 6:00 PM",
                ]
            },
        }
    ]
}

ROUTES_PAYLOAD = {
    "routes": [
        {
            "distanceMeters": 5432,
            "duration": "1234s",
            "polyline": {"encodedPolyline": "abc~encoded~xyz"},
        }
    ]
}


# ===========================================================================
# Weather tool tests
# ===========================================================================


class TestWeatherSuccess:
    @pytest.mark.anyio
    async def test_returns_forecast_with_correct_structure(self):
        transport = json_transport(200, WEATHER_PAYLOAD)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
            _transport=transport,
        )
        assert result.timezone == "Europe/Paris"
        assert result.latitude == 48.8566
        assert result.longitude == 2.3522
        assert len(result.days) == 2

    @pytest.mark.anyio
    async def test_first_day_parsed_correctly(self):
        transport = json_transport(200, WEATHER_PAYLOAD)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
            _transport=transport,
        )
        day = result.days[0]
        assert day.date == date(2025, 6, 1)
        assert day.condition == WeatherCondition.CLEAR
        assert day.weather_code == 0
        assert day.temperature_max == 22.5
        assert day.temperature_min == 15.0
        assert day.precipitation_mm == 0.0
        assert day.precipitation_probability == 5

    @pytest.mark.anyio
    async def test_second_day_rain_condition(self):
        transport = json_transport(200, WEATHER_PAYLOAD)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
            _transport=transport,
        )
        day = result.days[1]
        assert day.condition == WeatherCondition.RAIN
        assert day.weather_code == 63

    @pytest.mark.anyio
    async def test_wmo_code_mapping_thunderstorm(self):
        payload = {
            **WEATHER_PAYLOAD,
            "daily": {
                **WEATHER_PAYLOAD["daily"],
                "time": ["2025-06-01"],
                "weather_code": [95],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [15.0],
                "precipitation_sum": [5.0],
                "precipitation_probability_max": [90],
            },
        }
        transport = json_transport(200, payload)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 1),
            _transport=transport,
        )
        assert result.days[0].condition == WeatherCondition.THUNDERSTORM

    @pytest.mark.anyio
    async def test_unknown_wmo_code_maps_to_unknown(self):
        payload = {
            **WEATHER_PAYLOAD,
            "daily": {
                **WEATHER_PAYLOAD["daily"],
                "time": ["2025-06-01"],
                "weather_code": [999],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [15.0],
                "precipitation_sum": [0.0],
                "precipitation_probability_max": [0],
            },
        }
        transport = json_transport(200, payload)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 1),
            _transport=transport,
        )
        assert result.days[0].condition == WeatherCondition.UNKNOWN

    @pytest.mark.anyio
    async def test_none_precipitation_probability_defaults_to_zero(self):
        """Open-Meteo may return null for precipitation_probability_max."""
        payload = {
            **WEATHER_PAYLOAD,
            "daily": {
                **WEATHER_PAYLOAD["daily"],
                "time": ["2025-06-01"],
                "weather_code": [0],
                "temperature_2m_max": [20.0],
                "temperature_2m_min": [15.0],
                "precipitation_sum": [0.0],
                "precipitation_probability_max": [None],
            },
        }
        transport = json_transport(200, payload)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 1),
            _transport=transport,
        )
        assert result.days[0].precipitation_probability == 0

    @pytest.mark.anyio
    async def test_json_serialization(self):
        transport = json_transport(200, WEATHER_PAYLOAD)
        result = await get_weather_forecast(
            48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
            _transport=transport,
        )
        data = result.model_dump(mode="json")
        assert data["days"][0]["date"] == "2025-06-01"
        assert data["days"][0]["condition"] == "clear"


class TestWeatherValidation:
    @pytest.mark.anyio
    async def test_latitude_too_high_raises(self):
        with pytest.raises(WeatherError, match="latitude"):
            await get_weather_forecast(91, 0, date(2025, 6, 1), date(2025, 6, 2))

    @pytest.mark.anyio
    async def test_latitude_too_low_raises(self):
        with pytest.raises(WeatherError, match="latitude"):
            await get_weather_forecast(-91, 0, date(2025, 6, 1), date(2025, 6, 2))

    @pytest.mark.anyio
    async def test_longitude_too_high_raises(self):
        with pytest.raises(WeatherError, match="longitude"):
            await get_weather_forecast(0, 181, date(2025, 6, 1), date(2025, 6, 2))

    @pytest.mark.anyio
    async def test_longitude_too_low_raises(self):
        with pytest.raises(WeatherError, match="longitude"):
            await get_weather_forecast(0, -181, date(2025, 6, 1), date(2025, 6, 2))

    @pytest.mark.anyio
    async def test_end_before_start_raises(self):
        with pytest.raises(WeatherError, match="end_date"):
            await get_weather_forecast(
                48.8566, 2.3522, date(2025, 6, 7), date(2025, 6, 1)
            )


class TestWeatherErrors:
    @pytest.mark.anyio
    async def test_timeout_raises_weather_error(self):
        transport = error_transport(httpx2.ConnectTimeout("timed out"))
        with pytest.raises(WeatherError, match="timed out"):
            await get_weather_forecast(
                48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
                _transport=transport,
            )

    @pytest.mark.anyio
    async def test_network_error_raises_weather_error(self):
        transport = error_transport(httpx2.ConnectError("connection refused"))
        with pytest.raises(WeatherError, match="Network error"):
            await get_weather_forecast(
                48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
                _transport=transport,
            )

    @pytest.mark.anyio
    async def test_http_500_raises_weather_error(self):
        transport = json_transport(500, {"error": "internal server error"})
        with pytest.raises(WeatherError, match="HTTP 500"):
            await get_weather_forecast(
                48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
                _transport=transport,
            )

    @pytest.mark.anyio
    async def test_malformed_response_raises_weather_error(self):
        transport = json_transport(200, {"unexpected_key": "no daily data"})
        with pytest.raises(WeatherError, match="Unexpected"):
            await get_weather_forecast(
                48.8566, 2.3522, date(2025, 6, 1), date(2025, 6, 2),
                _transport=transport,
            )


# ===========================================================================
# Places tool tests
# ===========================================================================


class TestPlacesSuccess:
    @pytest.mark.anyio
    async def test_returns_list_of_places(self):
        transport = json_transport(200, PLACES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await search_places("museums in Paris", _transport=transport)
        assert len(result) == 1

    @pytest.mark.anyio
    async def test_place_fields_parsed_correctly(self):
        transport = json_transport(200, PLACES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await search_places("museums in Paris", _transport=transport)
        place = result[0]
        assert place.place_id == "ChIJLU7jZClu5kcR4PcOOO6p3I0"
        assert place.name == "Louvre Museum"
        assert place.address == "Rue de Rivoli, 75001 Paris, France"
        assert place.latitude == 48.8606
        assert place.longitude == 2.3376
        assert place.rating == 4.7
        assert place.price_level == "moderate"
        assert "museum" in place.types
        assert place.primary_type == "museum"
        assert len(place.weekday_descriptions) == 2

    @pytest.mark.anyio
    async def test_geographic_bias_included_in_request(self):
        """Verify the location bias is present in the outgoing request body."""
        captured_request: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured_request.append(request)
            return httpx2.Response(200, json=PLACES_PAYLOAD)

        transport = httpx2.MockTransport(handler)
        with patch.object(settings, "google_api_key", "test-api-key"):
            await search_places(
                "museums", latitude=48.8566, longitude=2.3522, _transport=transport
            )
        import json
        body = json.loads(captured_request[0].content)
        assert "locationBias" in body
        assert body["locationBias"]["circle"]["center"]["latitude"] == 48.8566

    @pytest.mark.anyio
    async def test_missing_optional_fields_are_none(self):
        """A place with no rating, priceLevel, types, or opening hours."""
        minimal_payload = {
            "places": [
                {
                    "id": "place-minimal",
                    "displayName": {"text": "Minimal Place"},
                    "formattedAddress": "123 Street",
                    "location": {"latitude": 1.0, "longitude": 2.0},
                }
            ]
        }
        transport = json_transport(200, minimal_payload)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await search_places("something", _transport=transport)
        place = result[0]
        assert place.rating is None
        assert place.price_level is None
        assert place.types == []
        assert place.primary_type is None
        assert place.weekday_descriptions == []

    @pytest.mark.anyio
    async def test_max_results_capped_at_20(self):
        captured: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured.append(request)
            return httpx2.Response(200, json={"places": []})

        transport = httpx2.MockTransport(handler)
        with patch.object(settings, "google_api_key", "test-api-key"):
            await search_places("query", max_results=100, _transport=transport)
        import json
        body = json.loads(captured[0].content)
        assert body["maxResultCount"] == 20

    @pytest.mark.anyio
    async def test_empty_results_returns_empty_list(self):
        transport = json_transport(200, {"places": []})
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await search_places("nothing here", _transport=transport)
        assert result == []

    @pytest.mark.anyio
    async def test_no_places_key_returns_empty_list(self):
        transport = json_transport(200, {})
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await search_places("query", _transport=transport)
        assert result == []

    @pytest.mark.anyio
    async def test_json_serialization_of_place(self):
        transport = json_transport(200, PLACES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await search_places("museums in Paris", _transport=transport)
        data = result[0].model_dump(mode="json")
        assert data["place_id"] == "ChIJLU7jZClu5kcR4PcOOO6p3I0"
        assert isinstance(data["rating"], float)


class TestPlacesValidation:
    @pytest.mark.anyio
    async def test_invalid_latitude_raises(self):
        with pytest.raises(PlacesError, match="latitude"):
            await search_places("query", latitude=91, longitude=0)

    @pytest.mark.anyio
    async def test_invalid_longitude_raises(self):
        with pytest.raises(PlacesError, match="longitude"):
            await search_places("query", latitude=0, longitude=181)

    @pytest.mark.anyio
    async def test_latitude_without_longitude_raises(self):
        with pytest.raises(PlacesError, match="both"):
            await search_places("query", latitude=48.8566)

    @pytest.mark.anyio
    async def test_longitude_without_latitude_raises(self):
        with pytest.raises(PlacesError, match="both"):
            await search_places("query", longitude=2.3522)

    @pytest.mark.anyio
    async def test_missing_api_key_raises(self):
        with patch.object(settings, "google_api_key", ""):
            with pytest.raises(PlacesError, match="API key"):
                await search_places("museums")


class TestPlacesErrors:
    @pytest.mark.anyio
    async def test_timeout_raises_places_error(self):
        transport = error_transport(httpx2.ConnectTimeout("timed out"))
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(PlacesError, match="timed out"):
                await search_places("museums", _transport=transport)

    @pytest.mark.anyio
    async def test_network_error_raises_places_error(self):
        transport = error_transport(httpx2.ConnectError("connection refused"))
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(PlacesError, match="Network error"):
                await search_places("museums", _transport=transport)

    @pytest.mark.anyio
    async def test_http_403_raises_places_error(self):
        transport = json_transport(403, {"error": {"status": "PERMISSION_DENIED"}})
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(PlacesError, match="HTTP 403"):
                await search_places("museums", _transport=transport)

    @pytest.mark.anyio
    async def test_malformed_response_raises_places_error(self):
        """A place entry missing the required 'id' field."""
        transport = json_transport(200, {"places": [{"no_id_field": True}]})
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(PlacesError, match="Unexpected"):
                await search_places("museums", _transport=transport)


# ===========================================================================
# Routing tool tests
# ===========================================================================


class TestRoutingSuccess:
    @pytest.mark.anyio
    async def test_drive_route_parsed_correctly(self):
        transport = json_transport(200, ROUTES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await get_route(
                48.8566, 2.3522, 48.8738, 2.2950,
                TravelMode.DRIVE,
                _transport=transport,
            )
        assert result.distance_meters == 5432
        assert result.duration_seconds == 1234
        assert result.travel_mode == TravelMode.DRIVE
        assert result.polyline == "abc~encoded~xyz"
        assert result.origin_lat == 48.8566
        assert result.destination_lat == 48.8738

    @pytest.mark.anyio
    async def test_walk_mode(self):
        transport = json_transport(200, ROUTES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await get_route(
                48.8566, 2.3522, 48.8738, 2.2950,
                TravelMode.WALK,
                _transport=transport,
            )
        assert result.travel_mode == TravelMode.WALK

    @pytest.mark.anyio
    async def test_bicycle_mode(self):
        transport = json_transport(200, ROUTES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await get_route(
                48.8566, 2.3522, 48.8738, 2.2950,
                TravelMode.BICYCLE,
                _transport=transport,
            )
        assert result.travel_mode == TravelMode.BICYCLE

    @pytest.mark.anyio
    async def test_transit_mode(self):
        transport = json_transport(200, ROUTES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await get_route(
                48.8566, 2.3522, 48.8738, 2.2950,
                TravelMode.TRANSIT,
                _transport=transport,
            )
        assert result.travel_mode == TravelMode.TRANSIT

    @pytest.mark.anyio
    async def test_travel_mode_sent_to_api(self):
        """Verify the Google API travel mode string is sent correctly."""
        captured: list[httpx2.Request] = []

        def handler(request: httpx2.Request) -> httpx2.Response:
            captured.append(request)
            return httpx2.Response(200, json=ROUTES_PAYLOAD)

        transport = httpx2.MockTransport(handler)
        with patch.object(settings, "google_api_key", "test-api-key"):
            await get_route(
                48.8566, 2.3522, 48.8738, 2.2950,
                TravelMode.WALK,
                _transport=transport,
            )
        import json
        body = json.loads(captured[0].content)
        assert body["travelMode"] == "WALK"

    @pytest.mark.anyio
    async def test_no_polyline_when_absent(self):
        payload = {
            "routes": [
                {
                    "distanceMeters": 1000,
                    "duration": "300s",
                }
            ]
        }
        transport = json_transport(200, payload)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await get_route(
                48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
            )
        assert result.polyline is None

    @pytest.mark.anyio
    async def test_json_serialization(self):
        transport = json_transport(200, ROUTES_PAYLOAD)
        with patch.object(settings, "google_api_key", "test-api-key"):
            result = await get_route(
                48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
            )
        data = result.model_dump(mode="json")
        assert data["travel_mode"] == "drive"
        assert isinstance(data["distance_meters"], int)


class TestRoutingValidation:
    @pytest.mark.anyio
    async def test_invalid_origin_latitude_raises(self):
        with pytest.raises(RoutingError, match="origin latitude"):
            await get_route(91, 0, 0, 0)

    @pytest.mark.anyio
    async def test_invalid_origin_longitude_raises(self):
        with pytest.raises(RoutingError, match="origin longitude"):
            await get_route(0, 181, 0, 0)

    @pytest.mark.anyio
    async def test_invalid_destination_latitude_raises(self):
        with pytest.raises(RoutingError, match="destination latitude"):
            await get_route(0, 0, -91, 0)

    @pytest.mark.anyio
    async def test_invalid_destination_longitude_raises(self):
        with pytest.raises(RoutingError, match="destination longitude"):
            await get_route(0, 0, 0, -181)

    @pytest.mark.anyio
    async def test_missing_api_key_raises(self):
        with patch.object(settings, "google_api_key", ""):
            with pytest.raises(RoutingError, match="API key"):
                await get_route(48.8566, 2.3522, 48.8738, 2.2950)


class TestRoutingErrors:
    @pytest.mark.anyio
    async def test_timeout_raises_routing_error(self):
        transport = error_transport(httpx2.ConnectTimeout("timed out"))
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(RoutingError, match="timed out"):
                await get_route(
                    48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
                )

    @pytest.mark.anyio
    async def test_network_error_raises_routing_error(self):
        transport = error_transport(httpx2.ConnectError("connection refused"))
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(RoutingError, match="Network error"):
                await get_route(
                    48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
                )

    @pytest.mark.anyio
    async def test_http_400_raises_routing_error(self):
        transport = json_transport(400, {"error": {"status": "INVALID_ARGUMENT"}})
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(RoutingError, match="HTTP 400"):
                await get_route(
                    48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
                )

    @pytest.mark.anyio
    async def test_empty_routes_array_raises_routing_error(self):
        transport = json_transport(200, {"routes": []})
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(RoutingError, match="No routes"):
                await get_route(
                    48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
                )

    @pytest.mark.anyio
    async def test_malformed_response_raises_routing_error(self):
        # A non-numeric duration string causes float() to raise ValueError,
        # which the parser converts to RoutingError.
        transport = json_transport(200, {"routes": [{"duration": "not-a-number"}]})
        with patch.object(settings, "google_api_key", "test-api-key"):
            with pytest.raises(RoutingError, match="Unexpected"):
                await get_route(
                    48.8566, 2.3522, 48.8738, 2.2950, _transport=transport
                )


# ===========================================================================
# Geocoding tool tests
# ===========================================================================

GEOCODING_PAYLOAD = {
    "results": [
        {
            "id": 2988507,
            "name": "Paris",
            "latitude": 48.85341,
            "longitude": 2.3488,
            "country_code": "FR",
            "country": "France",
            "admin1": "Île-de-France",
            "timezone": "Europe/Paris",
            "population": 2138551,
        }
    ]
}


class TestGeocodingSuccess:
    @pytest.mark.anyio
    async def test_returns_best_match(self):
        transport = json_transport(200, GEOCODING_PAYLOAD)
        result = await geocode_location("Paris, France", _transport=transport)
        assert result.name == "Paris"
        assert result.latitude == 48.85341
        assert result.longitude == 2.3488
        assert result.country == "France"
        assert result.country_code == "FR"
        assert result.admin1 == "Île-de-France"
        assert result.timezone == "Europe/Paris"

    @pytest.mark.anyio
    async def test_missing_optional_fields_are_none(self):
        minimal = {
            "results": [
                {
                    "id": 1,
                    "name": "Somewhere",
                    "latitude": 10.0,
                    "longitude": 20.0,
                    "country": "Testland",
                }
            ]
        }
        transport = json_transport(200, minimal)
        result = await geocode_location("Somewhere", _transport=transport)
        assert result.country_code is None
        assert result.admin1 is None
        assert result.timezone is None

    @pytest.mark.anyio
    async def test_whitespace_trimmed_from_query(self):
        """Surrounding whitespace should not cause an error."""
        transport = json_transport(200, GEOCODING_PAYLOAD)
        result = await geocode_location("  Paris, France  ", _transport=transport)
        assert result.name == "Paris"

    @pytest.mark.anyio
    async def test_json_serialization(self):
        transport = json_transport(200, GEOCODING_PAYLOAD)
        result = await geocode_location("Paris, France", _transport=transport)
        data = result.model_dump(mode="json")
        assert data["name"] == "Paris"
        assert isinstance(data["latitude"], float)
        assert data["country_code"] == "FR"


class TestGeocodingNoResults:
    @pytest.mark.anyio
    async def test_empty_results_array_raises(self):
        transport = json_transport(200, {"results": []})
        with pytest.raises(GeocodingError, match="No location found"):
            await geocode_location("xyzzy-nonexistent", _transport=transport)

    @pytest.mark.anyio
    async def test_missing_results_key_raises(self):
        # Open-Meteo returns {} (no key) when nothing matches.
        transport = json_transport(200, {})
        with pytest.raises(GeocodingError, match="No location found"):
            await geocode_location("xyzzy-nonexistent", _transport=transport)


class TestGeocodingValidation:
    @pytest.mark.anyio
    async def test_empty_string_raises(self):
        with pytest.raises(GeocodingError, match="empty"):
            await geocode_location("")

    @pytest.mark.anyio
    async def test_whitespace_only_raises(self):
        with pytest.raises(GeocodingError, match="empty"):
            await geocode_location("   ")


class TestGeocodingErrors:
    @pytest.mark.anyio
    async def test_timeout_raises_geocoding_error(self):
        transport = error_transport(httpx2.ConnectTimeout("timed out"))
        with pytest.raises(GeocodingError, match="timed out"):
            await geocode_location("Paris", _transport=transport)

    @pytest.mark.anyio
    async def test_network_error_raises_geocoding_error(self):
        transport = error_transport(httpx2.ConnectError("connection refused"))
        with pytest.raises(GeocodingError, match="Network error"):
            await geocode_location("Paris", _transport=transport)

    @pytest.mark.anyio
    async def test_http_500_raises_geocoding_error(self):
        transport = json_transport(500, {"reason": "server error"})
        with pytest.raises(GeocodingError, match="HTTP 500"):
            await geocode_location("Paris", _transport=transport)

    @pytest.mark.anyio
    async def test_malformed_response_raises_geocoding_error(self):
        # A result entry missing required "name" key.
        transport = json_transport(200, {"results": [{"latitude": 1.0}]})
        with pytest.raises(GeocodingError, match="Unexpected"):
            await geocode_location("Paris", _transport=transport)
