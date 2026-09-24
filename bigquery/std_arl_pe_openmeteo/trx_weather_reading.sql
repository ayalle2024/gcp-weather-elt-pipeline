CREATE TABLE IF NOT EXISTS `std_arl_pe_openmeteo.trx_weather_reading` (
  location_id            STRING NOT NULL OPTIONS (description = "Llave foránea hacia ori_mtr_location.location_id."),
  observed_at            TIMESTAMP OPTIONS (description = "Timestamp de la observación del clima."),
  temperature_c          FLOAT64 OPTIONS (description = "Temperatura del aire a 2m, en grados Celsius."),
  relative_humidity_pct  FLOAT64 OPTIONS (description = "Humedad relativa a 2m, en porcentaje."),
  wind_speed_kmh         FLOAT64 OPTIONS (description = "Velocidad del viento a 10m, en km/h."),
  ingestion_timestamp    TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC en que se ingirió este registro. Es la columna de particionamiento.")
)
PARTITION BY DATE(ingestion_timestamp)
CLUSTER BY location_id
OPTIONS (description = "Tabla transaccional: una lectura horaria de clima validada por ciudad, con nombres de campo estandarizados.");
