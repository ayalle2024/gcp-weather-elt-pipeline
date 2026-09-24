from flask import Blueprint, jsonify

from src.app.core.config import LOG_SEPARATOR, SERVICE_NAME
from src.app.integrations.bigquery.main import BigQueryInsertError
from src.app.integrations.storage.main import StorageUploadError
from src.app.services.weather_service import run_weather_ingestion
from src.app.utils.common import safe_json_dumps
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

weather_bp = Blueprint("weather", __name__)


@weather_bp.route("/", methods=["GET", "POST"])
@weather_bp.route("/weather-ingest", methods=["GET", "POST"])
def process_weather_ingestion():
    logger.info(LOG_SEPARATOR)
    logger.info("INICIO CR CONSUMO OPENMETEO API")
    logger.info(LOG_SEPARATOR)

    try:
        result = run_weather_ingestion()

        response = {
            "status": "success",
            "service": SERVICE_NAME,
            "payload": result,
        }

        logger.info("Mensaje exacto de respuesta desde Cloud Run:")
        logger.info(safe_json_dumps(response))

        logger.info(LOG_SEPARATOR)
        logger.info("FIN CR CONSUMO OPENMETEO API OK")
        logger.info(LOG_SEPARATOR)

        return jsonify(response), 200

    except (StorageUploadError, BigQueryInsertError) as e:
        logger.exception("Error de integración en Cloud Run")
        logger.info(LOG_SEPARATOR)
        logger.info("FIN CR CONSUMO OPENMETEO API INTEGRATION_ERROR")
        logger.info(LOG_SEPARATOR)
        return jsonify({"error": "Integration Error", "detail": str(e)}), 502

    except Exception as e:
        logger.exception("Error en Cloud Run")
        logger.info(LOG_SEPARATOR)
        logger.info("FIN CR CONSUMO OPENMETEO API ERROR")
        logger.info(LOG_SEPARATOR)
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500
