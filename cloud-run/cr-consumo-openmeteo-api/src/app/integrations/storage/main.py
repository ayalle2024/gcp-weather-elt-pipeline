"""Cliente para subir el payload crudo a la zona raw de Cloud Storage."""

import json
from datetime import datetime

from google.cloud import storage

from src.app.core.config import GCS_BUCKET_NAME, SERVICE_NAME
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)


class StorageUploadError(RuntimeError):
    """Error subiendo el payload crudo a Cloud Storage."""


def upload_raw_payload(raw_payload: dict, location_id: str, ingestion_ts: datetime) -> str:
    """Sube el JSON crudo tal cual llega de la fuente, sin transformar.

    Ruta según la taxonomía de buckets raw: <file_table_name>/in/<fecha>/<archivo_timestamp>
    """
    date_partition = ingestion_ts.strftime("%Y%m%d")
    file_name = f"weather_{location_id}_{ingestion_ts.strftime('%Y%m%d%H%M%S')}.json"
    blob_path = f"weather_current/in/{date_partition}/{file_name}"

    try:
        client = storage.Client()
        bucket = client.bucket(GCS_BUCKET_NAME)
        blob = bucket.blob(blob_path)
        blob.upload_from_string(json.dumps(raw_payload), content_type="application/json")
    except Exception as e:  # noqa: BLE001
        raise StorageUploadError(
            f"Fallo subiendo payload crudo a gs://{GCS_BUCKET_NAME}/{blob_path}: {e}"
        ) from e

    logger.info("Payload crudo subido a gs://%s/%s", GCS_BUCKET_NAME, blob_path)
    return blob_path
