CREATE TABLE IF NOT EXISTS `std_arl_pe_openmeteo.ori_mtr_location` (
  location_id     STRING NOT NULL OPTIONS (description = "Llave primaria: código corto que identifica la ciudad."),
  location_name   STRING NOT NULL OPTIONS (description = "Nombre legible de la ciudad."),
  latitude        FLOAT64 OPTIONS (description = "Latitud de la ciudad, en grados decimales."),
  longitude       FLOAT64 OPTIONS (description = "Longitud de la ciudad, en grados decimales."),
  country         STRING OPTIONS (description = "País de la ciudad. Actualmente fijo en 'Peru' al momento de la carga.")
)
OPTIONS (description = "Maestro de datos: una fila por ciudad monitoreada. Maestro propio del negocio, no es dato de referencia transversal.");
