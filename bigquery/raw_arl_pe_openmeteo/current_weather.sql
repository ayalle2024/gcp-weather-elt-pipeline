CREATE TABLE IF NOT EXISTS `raw_arl_pe_openmeteo.current_weather` (
  location_id            STRING NOT NULL OPTIONS (description = "Código corto que identifica la ciudad monitoreada (ej. LIM, AQP, TRU, CUS)."),
  location_name          STRING NOT NULL OPTIONS (description = "Nombre legible de la ciudad."),
  latitude                FLOAT64 OPTIONS (description = "Latitud de la ciudad, en grados decimales."),
  longitude               FLOAT64 OPTIONS (description = "Longitud de la ciudad, en grados decimales."),
  time                    TIMESTAMP OPTIONS (description = "Timestamp de la observación tal como lo devuelve la API fuente, antes de estandarizar."),
  temperature_2m          FLOAT64 OPTIONS (description = "Temperatura del aire a 2m, en grados Celsius. Nombre de campo original de Open-Meteo."),
  relative_humidity_2m    FLOAT64 OPTIONS (description = "Humedad relativa a 2m, en porcentaje. Nombre de campo original de Open-Meteo."),
  wind_speed_10m          FLOAT64 OPTIONS (description = "Velocidad del viento a 10m, en km/h. Nombre de campo original de Open-Meteo."),
  ingestion_timestamp     TIMESTAMP NOT NULL OPTIONS (description = "Timestamp UTC en que el servicio Cloud Run ingirió este registro. Es la columna de particionamiento.")
)
PARTITION BY DATE(ingestion_timestamp)
CLUSTER BY location_id
OPTIONS (description = "Tabla raw: por ciudad y por ejecución, 1 fila del bloque 'current' + 1 fila por hora del bloque 'hourly' de Open-Meteo, con los nombres de campo originales. Sin validación aplicada.");
