"""Lógica de negocio: orquesta fetch -> subir crudo -> limpiar -> validar -> insertar.

Cada ejecución guarda 2 cosas por ciudad:
  - La lectura puntual de 'current' (el clima justo ahora).
  - Las ~168 horas de pronóstico de 'hourly' (7 días), para tener volumen
    suficiente de datos sin depender de acumular corrida por corrida.

Ruteo de capas:
  - build_raw_row() / build_hourly_raw_rows()  -> capa raw (raw_arl_pe_openmeteo.current_weather)
  - clean_record()                              -> capa estandarizada (std_arl_pe_openmeteo.trx_weather_reading)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.app.core.config import SERVICE_NAME
from src.app.integrations.bigquery.main import insert_raw_weather, insert_standard_weather
from src.app.integrations.open_meteo.main import OpenMeteoError, fetch_weather
from src.app.integrations.storage.main import upload_raw_payload
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

# Un pequeño set fijo de ciudades mantiene el demo rápido y dentro del free tier.
CITIES = [
    {"location_id": "LIM", "name": "Lima", "lat": -12.0464, "lon": -77.0428},
    {"location_id": "AQP", "name": "Arequipa", "lat": -16.4090, "lon": -71.5375},
    {"location_id": "TRU", "name": "Trujillo", "lat": -8.1116, "lon": -79.0290},
    {"location_id": "CUS", "name": "Cusco", "lat": -13.5320, "lon": -71.9675},
]


def build_raw_row(city: dict, raw_payload: dict, ingestion_ts: datetime) -> dict:
    """Fila de la capa raw: mismos nombres de campo que devuelve Open-Meteo, sin limpiar."""
    current = raw_payload.get("current", {})

    return {
        "location_id": city["location_id"],
        "location_name": city["name"],
        "latitude": city["lat"],
        "longitude": city["lon"],
        "time": current.get("time"),
        "temperature_2m": current.get("temperature_2m"),
        "relative_humidity_2m": current.get("relative_humidity_2m"),
        "wind_speed_10m": current.get("wind_speed_10m"),
        "ingestion_timestamp": ingestion_ts.isoformat(),
    }


def build_hourly_raw_rows(city: dict, raw_payload: dict, ingestion_ts: datetime) -> List[dict]:
    """Filas de la capa raw a partir del bloque 'hourly' (pronóstico ~7 días):
    una fila por hora, mismos nombres de campo que build_raw_row()."""
    hourly = raw_payload.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    humidity = hourly.get("relative_humidity_2m", [])
    wind = hourly.get("wind_speed_10m", [])

    rows = []
    for i, observed_time in enumerate(times):
        rows.append({
            "location_id": city["location_id"],
            "location_name": city["name"],
            "latitude": city["lat"],
            "longitude": city["lon"],
            "time": observed_time,
            "temperature_2m": temps[i] if i < len(temps) else None,
            "relative_humidity_2m": humidity[i] if i < len(humidity) else None,
            "wind_speed_10m": wind[i] if i < len(wind) else None,
            "ingestion_timestamp": ingestion_ts.isoformat(),
        })
    return rows


def clean_record(raw_row: dict, ingestion_ts: datetime) -> dict:
    """Fila de la capa estandarizada: nombres y unidades ya estandarizados."""
    return {
        "location_id": raw_row["location_id"],
        "observed_at": raw_row["time"],
        "temperature_c": raw_row["temperature_2m"],
        "relative_humidity_pct": raw_row["relative_humidity_2m"],
        "wind_speed_kmh": raw_row["wind_speed_10m"],
        "ingestion_timestamp": ingestion_ts.isoformat(),
    }


def is_valid_record(record: dict) -> bool:
    """Regla de calidad mínima antes de que un registro entre a la capa estandarizada."""
    if record["observed_at"] is None or record["temperature_c"] is None:
        return False
    if not (-90 <= record["temperature_c"] <= 60):
        return False
    return True


def run_weather_ingestion() -> Dict[str, Any]:
    ingestion_ts = datetime.now(timezone.utc)

    raw_rows: List[dict] = []
    std_rows: List[dict] = []
    skipped = 0
    failed_cities: List[str] = []

    for city in CITIES:
        try:
            raw_payload = fetch_weather(city["lat"], city["lon"])
        except OpenMeteoError as e:
            logger.error("Fallo consultando Open-Meteo para %s: %s", city["name"], e)
            failed_cities.append(city["location_id"])
            continue

        upload_raw_payload(raw_payload, city["location_id"], ingestion_ts)

        city_raw_rows = [build_raw_row(city, raw_payload, ingestion_ts)]
        city_raw_rows.extend(build_hourly_raw_rows(city, raw_payload, ingestion_ts))
        raw_rows.extend(city_raw_rows)

        for raw_row in city_raw_rows:
            std_row = clean_record(raw_row, ingestion_ts)
            if is_valid_record(std_row):
                std_rows.append(std_row)
            else:
                skipped += 1

        logger.info("%s: %d filas (1 actual + %d de pronóstico)", city["name"], len(city_raw_rows), len(city_raw_rows) - 1)

    insert_raw_weather(raw_rows)
    insert_standard_weather(std_rows)

    return {
        "cities_fetched": len(CITIES) - len(failed_cities),
        "cities_failed": failed_cities,
        "rows_processed": len(std_rows),
        "rows_skipped": skipped,
        "ingestion_timestamp": ingestion_ts.isoformat(),
    }
