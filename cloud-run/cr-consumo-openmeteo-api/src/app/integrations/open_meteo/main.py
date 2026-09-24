"""Cliente para la API pública de Open-Meteo (https://open-meteo.com)."""

from typing import Any, Dict

import requests

from src.app.core.config import SERVICE_NAME
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class OpenMeteoError(RuntimeError):
    """Error consultando la API de Open-Meteo (red, timeout o respuesta inválida)."""


def fetch_weather(lat: float, lon: float, timeout: int = 15) -> Dict[str, Any]:
    logger.info("Consultando Open-Meteo (lat=%s, lon=%s)", lat, lon)

    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        # GMT (no "auto"): Open-Meteo devuelve las horas sin offset, y BigQuery
        # interpreta un TIMESTAMP sin offset como UTC. Con "auto" llegaban en hora
        # local de cada ciudad y quedaban guardadas 5 h corridas.
        "timezone": "GMT",
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise OpenMeteoError(f"Fallo de red consultando Open-Meteo: {e}") from e

    try:
        return response.json()
    except ValueError as e:
        raise OpenMeteoError(f"Respuesta inesperada de Open-Meteo (no es JSON válido): {e}") from e
