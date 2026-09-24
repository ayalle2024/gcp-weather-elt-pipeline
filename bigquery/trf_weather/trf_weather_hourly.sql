CREATE TABLE IF NOT EXISTS `trf_weather.trf_weather_hourly` (
  location_id            STRING NOT NULL OPTIONS (description = "Llave foránea hacia ori_mtr_location.location_id."),
  observed_at            TIMESTAMP NOT NULL OPTIONS (description = "Timestamp de la observación del clima. Es la columna de particionamiento."),
  temperature_c          FLOAT64 OPTIONS (description = "Temperatura del aire a 2m, en grados Celsius."),
  relative_humidity_pct  FLOAT64 OPTIONS (description = "Humedad relativa a 2m, en porcentaje."),
  wind_speed_kmh         FLOAT64 OPTIONS (description = "Velocidad del viento a 10m, en km/h."),
  ingestion_timestamp    TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC en que el registro fuente fue ingerido originalmente.")
)
PARTITION BY DATE(observed_at)
CLUSTER BY location_id
OPTIONS (description = "Tabla de hechos curada: una fila por observación horaria de clima por ubicación, cargada vía MERGE para mantenerse idempotente en reejecuciones.");
