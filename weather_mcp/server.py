from __future__ import annotations

from typing import Any, Dict, Optional

import httpx
from fastmcp import FastMCP

API_BASE = "https://api.open-meteo.com/v1/forecast"
MAX_HOURS = 168
REQUEST_TIMEOUT_SECONDS = 10.0

mcp = FastMCP("gigachat-mcp-weather")


def _validate_coordinates(latitude: float, longitude: float) -> tuple[float, float]:
    if not (-90.0 <= latitude <= 90.0):
        raise ValueError("latitude must be between -90 and 90")
    if not (-180.0 <= longitude <= 180.0):
        raise ValueError("longitude must be between -180 and 180")
    return float(latitude), float(longitude)


def _validate_hours(hours: int) -> int:
    if hours <= 0:
        raise ValueError("hours must be a positive integer")
    if hours > MAX_HOURS:
        raise ValueError(f"hours must be <= {MAX_HOURS}")
    return int(hours)


async def _fetch(params: Dict[str, Any]) -> Dict[str, Any]:
    transport = httpx.AsyncHTTPTransport(retries=2)
    timeout = httpx.Timeout(REQUEST_TIMEOUT_SECONDS)
    async with httpx.AsyncClient(transport=transport, timeout=timeout) as client:
        response = await client.get(API_BASE, params=params)
        response.raise_for_status()
        return response.json()


def _format_error(err: Exception) -> Dict[str, Any]:
    return {"error": str(err)}


@mcp.tool()
async def get_current_weather(
    latitude: float,
    longitude: float,
    timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Return the current temperature and wind speed for the given coordinates."""
    try:
        lat, lon = _validate_coordinates(latitude, longitude)
    except ValueError as exc:
        return _format_error(exc)

    params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,wind_speed_10m",
    }
    if timezone:
        params["timezone"] = timezone

    try:
        data = await _fetch(params)
    except httpx.HTTPStatusError as exc:
        return _format_error(
            Exception(f"API returned {exc.response.status_code}: {exc.response.text}")
        )
    except httpx.HTTPError as exc:
        return _format_error(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return _format_error(exc)

    return {
        "latitude": data.get("latitude", lat),
        "longitude": data.get("longitude", lon),
        "timezone": data.get("timezone", timezone),
        "current": data.get("current", {}),
        "units": {
            "temperature_2m": data.get("current_units", {}).get("temperature_2m"),
            "wind_speed_10m": data.get("current_units", {}).get("wind_speed_10m"),
        },
    }


@mcp.tool()
async def get_hourly_forecast(
    latitude: float,
    longitude: float,
    hours: int = 24,
    timezone: Optional[str] = None,
) -> Dict[str, Any]:
    """Return hourly temperature and humidity forecast for the next N hours."""
    try:
        lat, lon = _validate_coordinates(latitude, longitude)
        limit = _validate_hours(hours)
    except ValueError as exc:
        return _format_error(exc)

    params: Dict[str, Any] = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m",
    }
    if timezone:
        params["timezone"] = timezone

    try:
        data = await _fetch(params)
    except httpx.HTTPStatusError as exc:
        return _format_error(
            Exception(f"API returned {exc.response.status_code}: {exc.response.text}")
        )
    except httpx.HTTPError as exc:
        return _format_error(exc)
    except Exception as exc:  # pragma: no cover - defensive
        return _format_error(exc)

    hourly = data.get("hourly", {})
    trimmed_hourly = {}
    for key, values in hourly.items():
        if isinstance(values, list):
            trimmed_hourly[key] = values[:limit]
        else:
            trimmed_hourly[key] = values

    return {
        "latitude": data.get("latitude", lat),
        "longitude": data.get("longitude", lon),
        "timezone": data.get("timezone", timezone),
        "hours": limit,
        "hourly": trimmed_hourly,
        "units": data.get("hourly_units", {}),
    }


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
