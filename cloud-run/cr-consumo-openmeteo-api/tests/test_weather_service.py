from datetime import datetime, timezone

from src.app.services.weather_service import (
    build_hourly_raw_rows,
    build_raw_row,
    clean_record,
    is_valid_record,
)

SAMPLE_CITY = {"location_id": "LIM", "name": "Lima", "lat": -12.0464, "lon": -77.0428}


def test_build_raw_row_keeps_source_field_names():
    raw_payload = {
        "current": {
            "time": "2024-01-15T10:00",
            "temperature_2m": 24.5,
            "relative_humidity_2m": 78,
            "wind_speed_10m": 12.3,
        }
    }
    ts = datetime(2024, 1, 15, 10, 5, tzinfo=timezone.utc)

    row = build_raw_row(SAMPLE_CITY, raw_payload, ts)

    assert row["location_id"] == "LIM"
    assert row["temperature_2m"] == 24.5
    assert row["relative_humidity_2m"] == 78
    assert row["wind_speed_10m"] == 12.3
    assert row["ingestion_timestamp"] == ts.isoformat()


def test_build_hourly_raw_rows_returns_one_row_per_hour():
    raw_payload = {
        "hourly": {
            "time": ["2024-01-15T00:00", "2024-01-15T01:00"],
            "temperature_2m": [18.0, 17.5],
            "relative_humidity_2m": [80, 82],
            "wind_speed_10m": [10.0, 9.5],
        }
    }
    ts = datetime(2024, 1, 15, 10, 5, tzinfo=timezone.utc)

    rows = build_hourly_raw_rows(SAMPLE_CITY, raw_payload, ts)

    assert len(rows) == 2
    assert rows[0]["time"] == "2024-01-15T00:00"
    assert rows[0]["temperature_2m"] == 18.0
    assert rows[1]["time"] == "2024-01-15T01:00"
    assert rows[1]["temperature_2m"] == 17.5
    assert all(row["location_id"] == "LIM" for row in rows)


def test_build_hourly_raw_rows_handles_missing_hourly_block():
    rows = build_hourly_raw_rows(SAMPLE_CITY, {}, datetime.now(timezone.utc))
    assert rows == []


def test_clean_record_standardizes_field_names():
    ts = datetime(2024, 1, 15, 10, 5, tzinfo=timezone.utc)
    raw_row = {
        "location_id": "LIM",
        "time": "2024-01-15T10:00",
        "temperature_2m": 24.5,
        "relative_humidity_2m": 78,
        "wind_speed_10m": 12.3,
    }

    record = clean_record(raw_row, ts)

    assert record["location_id"] == "LIM"
    assert record["observed_at"] == "2024-01-15T10:00"
    assert record["temperature_c"] == 24.5
    assert record["relative_humidity_pct"] == 78
    assert record["wind_speed_kmh"] == 12.3


def test_valid_record_passes_quality_gate():
    record = {"observed_at": "2024-01-15T10:00", "temperature_c": 24.5}
    assert is_valid_record(record) is True


def test_missing_temperature_is_rejected():
    record = {"observed_at": "2024-01-15T10:00", "temperature_c": None}
    assert is_valid_record(record) is False


def test_missing_timestamp_is_rejected():
    record = {"observed_at": None, "temperature_c": 24.5}
    assert is_valid_record(record) is False


def test_unrealistic_temperature_is_rejected():
    record = {"observed_at": "2024-01-15T10:00", "temperature_c": 150.0}
    assert is_valid_record(record) is False


def test_boundary_temperatures_are_accepted():
    low = {"observed_at": "2024-01-15T10:00", "temperature_c": -90}
    high = {"observed_at": "2024-01-15T10:00", "temperature_c": 60}
    assert is_valid_record(low) is True
    assert is_valid_record(high) is True
