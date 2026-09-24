import os

# -------------------------------------------------------
# Configuración general
# -------------------------------------------------------


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Falta la variable de entorno obligatoria: {name}")
    return value


PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID", "arl-dtpr-dev-weth")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "cr-consumo-openmeteo-api")

# -------------------------------------------------------
# Cloud Storage
# -------------------------------------------------------
# Sin valor de respaldo: si falta, el servicio no arranca en vez de escribir
# silenciosamente en un bucket equivocado o inexistente.

GCS_BUCKET_NAME = _require_env("GCS_BUCKET_NAME")

# -------------------------------------------------------
# BigQuery — capa raw (espejo exacto de la fuente)
# -------------------------------------------------------

BQ_RAW_DATASET = os.environ.get("BQ_RAW_DATASET", "raw_arl_pe_openmeteo")
BQ_RAW_TABLE = os.environ.get("BQ_RAW_TABLE", "current_weather")

# -------------------------------------------------------
# BigQuery — capa estandarizada (limpia y validada)
# -------------------------------------------------------

BQ_STD_DATASET = os.environ.get("BQ_STD_DATASET", "std_arl_pe_openmeteo")
BQ_STD_TABLE = os.environ.get("BQ_STD_TABLE", "trx_weather_reading")

# -------------------------------------------------------
# Logging
# -------------------------------------------------------

LOG_SEPARATOR = "======================================"
