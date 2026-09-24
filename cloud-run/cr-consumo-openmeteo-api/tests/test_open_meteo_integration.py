from unittest.mock import Mock, patch

import pytest
import requests

from src.app.integrations.open_meteo.main import OpenMeteoError, fetch_weather


@patch("src.app.integrations.open_meteo.main.requests.get")
def test_fetch_weather_returns_json_on_success(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = {"current": {"temperature_2m": 20.0}}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = fetch_weather(-12.0464, -77.0428)

    assert result["current"]["temperature_2m"] == 20.0


@patch("src.app.integrations.open_meteo.main.requests.get")
def test_fetch_weather_requests_timestamps_in_gmt(mock_get):
    """BigQuery guarda un TIMESTAMP sin offset como UTC, así que la API debe devolver GMT."""
    mock_response = Mock()
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    fetch_weather(-12.0464, -77.0428)

    assert mock_get.call_args.kwargs["params"]["timezone"] == "GMT"


@patch("src.app.integrations.open_meteo.main.requests.get")
def test_fetch_weather_raises_open_meteo_error_on_network_failure(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("no network")

    with pytest.raises(OpenMeteoError):
        fetch_weather(-12.0464, -77.0428)


@patch("src.app.integrations.open_meteo.main.requests.get")
def test_fetch_weather_raises_open_meteo_error_on_invalid_json(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = ValueError("not json")
    mock_get.return_value = mock_response

    with pytest.raises(OpenMeteoError):
        fetch_weather(-12.0464, -77.0428)
