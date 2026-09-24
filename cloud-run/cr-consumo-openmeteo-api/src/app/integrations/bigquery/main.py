"""Cliente para insertar en las tablas raw y estandarizada de BigQuery."""

from typing import List

from google.cloud import bigquery

from src.app.core.config import (
    BQ_RAW_DATASET,
    BQ_RAW_TABLE,
    BQ_STD_DATASET,
    BQ_STD_TABLE,
    PROJECT_ID,
    SERVICE_NAME,
)
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

_client = None


class BigQueryInsertError(RuntimeError):
    """Error insertando filas en BigQuery."""


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT_ID)
    return _client


def _insert(table_id: str, rows: List[dict]) -> None:
    if not rows:
        return

    client = _get_client()
    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise BigQueryInsertError(f"Errores insertando en {table_id}: {errors}")

    logger.info("Insertadas %d filas en %s", len(rows), table_id)


def insert_raw_weather(rows: List[dict]) -> None:
    """Inserta en la capa raw, con los nombres de campo tal como vienen de Open-Meteo."""
    table_id = f"{PROJECT_ID}.{BQ_RAW_DATASET}.{BQ_RAW_TABLE}"
    _insert(table_id, rows)


def insert_standard_weather(rows: List[dict]) -> None:
    """Inserta en la capa estandarizada, ya validada y con nombres en inglés estandarizados."""
    table_id = f"{PROJECT_ID}.{BQ_STD_DATASET}.{BQ_STD_TABLE}"
    _insert(table_id, rows)
