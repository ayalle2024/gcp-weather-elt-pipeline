from unittest.mock import patch


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "cr-consumo-openmeteo-api"


@patch("src.app.api.routes.weather.run_weather_ingestion")
def test_weather_ingest_endpoint_success(mock_run, client):
    mock_run.return_value = {
        "cities_fetched": 4,
        "cities_failed": [],
        "rows_processed": 676,
        "rows_skipped": 0,
        "ingestion_timestamp": "2024-01-15T10:00:00+00:00",
    }

    response = client.post("/")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["payload"]["rows_processed"] == 676


@patch("src.app.api.routes.weather.run_weather_ingestion")
def test_weather_ingest_endpoint_handles_storage_error(mock_run, client):
    from src.app.integrations.storage.main import StorageUploadError

    mock_run.side_effect = StorageUploadError("gcs down")

    response = client.post("/")

    assert response.status_code == 502
    assert response.get_json()["error"] == "Integration Error"


@patch("src.app.api.routes.weather.run_weather_ingestion")
def test_weather_ingest_endpoint_handles_unexpected_error(mock_run, client):
    mock_run.side_effect = RuntimeError("boom")

    response = client.post("/")

    assert response.status_code == 500
    assert response.get_json()["error"] == "Internal Error"
