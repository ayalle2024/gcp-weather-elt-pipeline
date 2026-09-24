-- sq_transform_weather_standard_to_trf
-- BigQuery Scheduled Query del proyecto arl-dtpr-dev-weth, en modo On-demand:
-- no tiene horario propio. La dispara el Workflow orquestador-weather
-- (startManualRuns) solo después de que cr-consumo-openmeteo-api confirmó éxito.
-- Corre como sa-weather-sq-runtime.
--
-- Hace 2 cosas, ambas con MERGE para ser idempotente en reejecuciones:
--   1) Llena std_arl_pe_openmeteo.ori_mtr_location con las ciudades nuevas
--      vistas en la capa raw (una fila por ciudad, no cambia con el tiempo).
--   2) Llena trf_weather.trf_weather_hourly con las lecturas válidas de hoy
--      desde la capa estandarizada, evitando duplicar (location_id, observed_at).

-- Paso 1: maestro de ubicaciones (desde la capa raw, que sí trae nombre/lat/lon)
MERGE `std_arl_pe_openmeteo.ori_mtr_location` T
USING (
  SELECT DISTINCT
    location_id,
    location_name,
    latitude,
    longitude,
    'Peru' AS country
  FROM `raw_arl_pe_openmeteo.current_weather`
) S
ON T.location_id = S.location_id
WHEN NOT MATCHED THEN
  INSERT (location_id, location_name, latitude, longitude, country)
  VALUES (S.location_id, S.location_name, S.latitude, S.longitude, S.country);

-- Paso 2: tabla de hechos curada (desde la capa estandarizada de hoy)
MERGE `trf_weather.trf_weather_hourly` T
USING (
  SELECT
    location_id,
    observed_at,
    temperature_c,
    relative_humidity_pct,
    wind_speed_kmh,
    ingestion_timestamp
  FROM `std_arl_pe_openmeteo.trx_weather_reading`
  WHERE DATE(ingestion_timestamp) = CURRENT_DATE()
    AND temperature_c IS NOT NULL
    AND observed_at IS NOT NULL
) S
ON T.location_id = S.location_id AND T.observed_at = S.observed_at
WHEN NOT MATCHED THEN
  INSERT (location_id, observed_at, temperature_c, relative_humidity_pct, wind_speed_kmh, ingestion_timestamp)
  VALUES (S.location_id, S.observed_at, S.temperature_c, S.relative_humidity_pct, S.wind_speed_kmh, S.ingestion_timestamp);
