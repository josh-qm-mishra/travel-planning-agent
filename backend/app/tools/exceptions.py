class ToolError(Exception):
    """Base for all travel-tool failures."""


class WeatherError(ToolError):
    """Raised when the weather tool cannot fulfil a request."""


class PlacesError(ToolError):
    """Raised when the places tool cannot fulfil a request."""


class RoutingError(ToolError):
    """Raised when the routing tool cannot fulfil a request."""


class GeocodingError(ToolError):
    """Raised when the geocoding tool cannot fulfil a request."""
