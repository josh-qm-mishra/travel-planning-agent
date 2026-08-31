from datetime import date
from enum import StrEnum

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Weather
# ---------------------------------------------------------------------------


class WeatherCondition(StrEnum):
    CLEAR = "clear"
    PARTLY_CLOUDY = "partly_cloudy"
    OVERCAST = "overcast"
    FOG = "fog"
    DRIZZLE = "drizzle"
    RAIN = "rain"
    SNOW = "snow"
    THUNDERSTORM = "thunderstorm"
    UNKNOWN = "unknown"


class DailyWeather(BaseModel):
    date: date
    condition: WeatherCondition
    weather_code: int
    temperature_max: float
    temperature_min: float
    precipitation_mm: float
    precipitation_probability: int


class WeatherForecast(BaseModel):
    latitude: float
    longitude: float
    timezone: str
    days: list[DailyWeather]


# ---------------------------------------------------------------------------
# Places
# ---------------------------------------------------------------------------


class Place(BaseModel):
    place_id: str
    name: str
    address: str
    latitude: float
    longitude: float
    rating: float | None = None
    price_level: str | None = None
    types: list[str] = Field(default_factory=list)
    primary_type: str | None = None
    weekday_descriptions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Geocoding
# ---------------------------------------------------------------------------


class GeocodingLocation(BaseModel):
    name: str
    latitude: float
    longitude: float
    country: str
    country_code: str | None = None
    admin1: str | None = None
    timezone: str | None = None


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


class TravelMode(StrEnum):
    DRIVE = "drive"
    WALK = "walk"
    BICYCLE = "bicycle"
    TRANSIT = "transit"


class Route(BaseModel):
    origin_lat: float
    origin_lng: float
    destination_lat: float
    destination_lng: float
    travel_mode: TravelMode
    distance_meters: int
    duration_seconds: int
    polyline: str | None = None
