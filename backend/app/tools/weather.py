from datetime import date

import httpx2

from .exceptions import WeatherError
from .models import DailyWeather, WeatherCondition, WeatherForecast

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT = 10.0

# WMO Weather interpretation codes → simplified conditions.
# Full table: https://open-meteo.com/en/docs (WMO Weather interpretation codes)
_WMO_CONDITION: dict[int, WeatherCondition] = {
    0: WeatherCondition.CLEAR,
    1: WeatherCondition.PARTLY_CLOUDY,
    2: WeatherCondition.PARTLY_CLOUDY,
    3: WeatherCondition.OVERCAST,
    45: WeatherCondition.FOG,
    48: WeatherCondition.FOG,
    51: WeatherCondition.DRIZZLE,
    53: WeatherCondition.DRIZZLE,
    55: WeatherCondition.DRIZZLE,
    56: WeatherCondition.DRIZZLE,
    57: WeatherCondition.DRIZZLE,
    61: WeatherCondition.RAIN,
    63: WeatherCondition.RAIN,
    65: WeatherCondition.RAIN,
    66: WeatherCondition.RAIN,
    67: WeatherCondition.RAIN,
    71: WeatherCondition.SNOW,
    73: WeatherCondition.SNOW,
    75: WeatherCondition.SNOW,
    77: WeatherCondition.SNOW,
    80: WeatherCondition.RAIN,
    81: WeatherCondition.RAIN,
    82: WeatherCondition.RAIN,
    85: WeatherCondition.SNOW,
    86: WeatherCondition.SNOW,
    95: WeatherCondition.THUNDERSTORM,
    96: WeatherCondition.THUNDERSTORM,
    99: WeatherCondition.THUNDERSTORM,
}


async def get_weather_forecast(
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    *,
    _transport: httpx2.AsyncBaseTransport | None = None,
) -> WeatherForecast:
    """Fetch daily weather forecast from Open-Meteo for a date range.

    Raises WeatherError for invalid inputs and all provider/network failures.
    """
    if not (-90 <= latitude <= 90):
        raise WeatherError(f"Invalid latitude: {latitude}")
    if not (-180 <= longitude <= 180):
        raise WeatherError(f"Invalid longitude: {longitude}")
    if end_date < start_date:
        raise WeatherError("end_date cannot be before start_date")

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min,"
            "precipitation_sum,"
            "precipitation_probability_max"
        ),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "timezone": "auto",
    }

    client_kwargs: dict = {"timeout": _TIMEOUT}
    if _transport is not None:
        client_kwargs["transport"] = _transport

    try:
        async with httpx2.AsyncClient(**client_kwargs) as client:
            response = await client.get(_BASE_URL, params=params)
            response.raise_for_status()
    except httpx2.TimeoutException as e:
        raise WeatherError("Weather service request timed out") from e
    except httpx2.HTTPStatusError as e:
        raise WeatherError(
            f"Weather service returned HTTP {e.response.status_code}"
        ) from e
    except httpx2.NetworkError as e:
        raise WeatherError("Network error reaching weather service") from e
    except httpx2.RequestError as e:
        raise WeatherError(f"Request to weather service failed: {e}") from e

    return _parse_forecast(response.json(), latitude, longitude)


def _parse_forecast(data: dict, latitude: float, longitude: float) -> WeatherForecast:
    try:
        daily = data["daily"]
        days = [
            DailyWeather(
                date=date_str,
                condition=_WMO_CONDITION.get(code, WeatherCondition.UNKNOWN),
                weather_code=code,
                temperature_max=temp_max,
                temperature_min=temp_min,
                precipitation_mm=precip if precip is not None else 0.0,
                precipitation_probability=prob if prob is not None else 0,
            )
            for date_str, code, temp_max, temp_min, precip, prob in zip(
                daily["time"],
                daily["weather_code"],
                daily["temperature_2m_max"],
                daily["temperature_2m_min"],
                daily["precipitation_sum"],
                daily["precipitation_probability_max"],
            )
        ]
        return WeatherForecast(
            latitude=data.get("latitude", latitude),
            longitude=data.get("longitude", longitude),
            timezone=data.get("timezone", "UTC"),
            days=days,
        )
    except (KeyError, TypeError, ValueError) as e:
        raise WeatherError(f"Unexpected weather response format: {e}") from e
