# Documento Técnico de Despliegue
## Proyecto 1 — Weather ELT Pipeline (`arl-dtpr-dev-weth`)

**Autor:** Alvaro Yalle
**Organización:** Arla & Asociados
**Última actualización:** Septiembre 2026
**Versión:** 2 (evoluciona la v1 `gcp-cloudrun-weather-etl`, ver sección 14)

---

## 1. Resumen del proyecto

| Campo | Valor |
|---|---|
| Project ID | `arl-dtpr-dev-weth` |
| Número de proyecto | `<PROJECT_NUMBER>` |
| Región | `us-central1` (BigQuery Data Transfer en `us`) |
| Taxonomía | `<bu>-<capability>-<env>-<domain>` → `arl` (Arla & Asociados) · `dtpr` (Data Products) · `dev` (ambiente) · `weth` (dominio weather) |
| Patrón que demuestra | ELT orientado a eventos con Cloud Run + Cloud Storage + BigQuery en 3 capas (raw / standard / transformed), orquestado por un Cloud Workflow |
| Fuente de datos | API pública Open-Meteo (`https://api.open-meteo.com/v1/forecast`), sin API key |
| Ciudades monitoreadas | Lima (`LIM`), Arequipa (`AQP`), Trujillo (`TRU`), Cusco (`CUS`) |
| Volumen por ejecución | 4 ciudades × 169 filas (1 lectura actual + ~168 horas de pronóstico) ≈ 676 filas |
| Costo | $0.00 — todo dentro del free tier permanente de GCP |

### 1.1. Qué hace el proyecto, en una frase
Cada ejecución consulta el clima de 4 ciudades peruanas, guarda el JSON crudo en Cloud Storage, inserta los datos en una capa raw y en una capa estandarizada validada de BigQuery, y luego una Scheduled Query los consolida en una tabla de hechos curada y en un maestro de ciudades. Un Cloud Workflow encadena todo y confirma que cada paso terminó de verdad.

### 1.2. Inventario de componentes (9)

| # | Tipo | Nombre | Rol en el flujo |
|---|---|---|---|
| 1 | Cloud Scheduler | `job-trigger-weather-ingest` | Disparador horario (creado y pausado) |
| 2 | Cloud Workflow | `orquestador-weather` | Orquestador del pipeline |
| 3 | Cloud Run | `cr-consumo-openmeteo-api` | Ingesta: consulta la API, sube a GCS, inserta en BigQuery |
| 4 | Cloud Storage | `raw-arl-weth-pe-openmeteo-dev-<SUFFIX>` | Zona raw: JSON crudo |
| 5 | BigQuery (tabla) | `raw_arl_pe_openmeteo.current_weather` | Capa raw |
| 6 | BigQuery (tabla) | `std_arl_pe_openmeteo.trx_weather_reading` | Capa estandarizada, lecturas validadas |
| 7 | BigQuery Scheduled Query | `sq_transform_weather_standard_to_trf` | Transformación a tabla curada + maestro |
| 8 | BigQuery (tabla) | `std_arl_pe_openmeteo.ori_mtr_location` | Maestro de ciudades |
| 9 | BigQuery (tabla) | `trf_weather.trf_weather_hourly` | Tabla de hechos curada (consumo final) |

---

## 2. Arquitectura

```
Cloud Scheduler: job-trigger-weather-ingest   (cron 0 * * * *, America/Lima — PAUSADO)
        │  POST (OAuth, sa-weather-scheduler-invoker)
        ▼
Cloud Workflow: orquestador-weather           (identidad: sa-weather-workflow-runtime)
        │
        ├─► Paso 1: POST con OIDC a Cloud Run
        │        │
        │        ▼
        │   Cloud Run: cr-consumo-openmeteo-api   (privado, identidad: sa-weather-cloudrun-runtime)
        │        │
        │        ├─► Open-Meteo API (pública) — bloques 'current' + 'hourly' (~168 h)
        │        ├─► Cloud Storage  raw-arl-weth-pe-openmeteo-dev-…/weather_current/in/<fecha>/<archivo>.json
        │        ├─► BigQuery raw   raw_arl_pe_openmeteo.current_weather
        │        └─► BigQuery std   std_arl_pe_openmeteo.trx_weather_reading
        │
        ├─► Paso 2: verifica body.status == "success" (no solo HTTP 200)
        │
        ├─► Paso 3: dispara la Scheduled Query vía BigQuery Data Transfer API (startManualRuns)
        │        sq_transform_weather_standard_to_trf
        │              ├─► MERGE → std_arl_pe_openmeteo.ori_mtr_location
        │              └─► MERGE → trf_weather.trf_weather_hourly
        │
        └─► Paso 4: polling cada 10 s hasta SUCCEEDED / FAILED / CANCELLED
```

### 2.1. Orden real de ejecución
1. Workflow `orquestador-weather` (arranca con el botón Execute o lo dispara el Scheduler).
2. Cloud Run `cr-consumo-openmeteo-api` (consulta Open-Meteo).
3. Bucket de Cloud Storage (recibe el JSON crudo).
4. BigQuery `current_weather` (raw) y `trx_weather_reading` (std), insertadas por el Cloud Run.
5. Scheduled Query `sq_transform_weather_standard_to_trf` (corre **después** de que el Cloud Run terminó).
6. BigQuery `ori_mtr_location` y `trf_weather_hourly` (pobladas por la Scheduled Query).

---

## 3. Prerrequisitos

### 3.1. Cuenta y herramientas
- Cuenta de Google Cloud con facturación habilitada (necesaria incluso para el free tier).
- `gcloud` CLI autenticado, o Cloud Shell:
  ```bash
  gcloud auth login
  gcloud config set project arl-dtpr-dev-weth
  ```
- Python 3.11 (misma versión que la imagen del Dockerfile, para correr las pruebas antes de desplegar) y `uv` opcional para generar `requirements.txt`.

### 3.2. Habilitar las APIs
```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  cloudscheduler.googleapis.com \
  bigquery.googleapis.com \
  bigquerydatatransfer.googleapis.com \
  storage.googleapis.com \
  workflows.googleapis.com \
  iam.googleapis.com \
  --project=arl-dtpr-dev-weth
```

### 3.3. Nota sobre el service agent de Workflows
Si al desplegar el Workflow por primera vez aparece `Workflows service agent does not exist (Code: 9)`, es un error transitorio tras habilitar la API. Solución:
```bash
gcloud beta services identity create --service=workflows.googleapis.com --project=arl-dtpr-dev-weth
```

---

## 4. Notas de costo

| Servicio | Límite gratuito permanente | Uso en este proyecto |
|---|---|---|
| BigQuery | 1 TB consultas/mes + 10 GB almacenamiento | Cientos de filas por ejecución; muy por debajo |
| Cloud Storage | 5 GB (regiones US elegibles) | ~4 JSON pequeños por ejecución |
| Cloud Run | 2 M requests/mes, escala a cero | 1 request por ejecución |
| Cloud Workflows | 5 000 pasos internos/mes gratis | ~20 pasos por ejecución |
| Cloud Scheduler | 3 jobs gratis por cuenta de facturación | 1 job (pausado) |
| Cloud Build / Artifact Registry | Cuotas gratuitas mensuales | Solo al desplegar |

El costo real se verifica en **Facturación → Informes**, filtrando por el proyecto.

---

## 5. Cuentas de servicio (IAM)

Se aplica el principio de mínimo privilegio: una identidad por rol funcional. Detalle completo en [`service-accounts-es.md`](service-accounts-es.md).

| Cuenta | Origen | Usada por | Permisos |
|---|---|---|---|
| `sa-weather-scheduler-invoker` | Creada a propósito | Cloud Scheduler | `roles/workflows.invoker` (para disparar el Workflow) |
| `sa-weather-workflow-runtime` | Creada a propósito | El Workflow | `roles/run.invoker` sobre `cr-consumo-openmeteo-api` + rol personalizado `weatherTransferRunner` + `roles/logging.logWriter` |
| `sa-weather-cloudrun-runtime` | Creada a propósito | El Cloud Run | `roles/storage.objectCreator` (solo el bucket) + `WRITER` solo en los datasets `raw_` y `std_` |
| `sa-weather-sq-runtime` | Creada a propósito | La Scheduled Query | `roles/bigquery.jobUser` (proyecto) + `READER` en `raw_` + `WRITER` en `std_` y `trf_` |
| `sa-weather-cloudbuild` | Creada a propósito | Cloud Build (despliegues `--source`) | `roles/run.builder` |
| `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` | Automática (default) | **Ningún componente** | Sin roles de proyecto (se le retiró el `roles/editor` heredado) |

> **Hardening aplicado y validado (24/09/2026).** Ningún componente usa la cuenta default de Compute. Verificación: los jobs `scheduled_query_*` corren con `sa-weather-sq-runtime` (campo `user_email` en `INFORMATION_SCHEMA.JOBS_BY_PROJECT`), el último build corrió con `sa-weather-cloudbuild` y una ejecución completa del Workflow terminó en `SUCCEEDED` con 676 filas.

### 5.1. Creación de las cuentas
```bash
gcloud iam service-accounts create sa-weather-scheduler-invoker \
  --display-name="Scheduler invoker for weather Workflow" --project=arl-dtpr-dev-weth

gcloud iam service-accounts create sa-weather-workflow-runtime \
  --display-name="Runtime identity for orquestador-weather" --project=arl-dtpr-dev-weth

gcloud iam service-accounts create sa-weather-cloudrun-runtime \
  --display-name="Runtime identity for cr-consumo-openmeteo-api" --project=arl-dtpr-dev-weth

gcloud iam service-accounts create sa-weather-sq-runtime \
  --display-name="Runtime identity for sq_transform_weather_standard_to_trf" --project=arl-dtpr-dev-weth

gcloud iam service-accounts create sa-weather-cloudbuild \
  --display-name="Build identity for cr-consumo-openmeteo-api source deploys" --project=arl-dtpr-dev-weth
```

### 5.2. Permisos de `sa-weather-cloudrun-runtime`
```bash
BUCKET=raw-arl-weth-pe-openmeteo-dev-<SUFFIX>

gcloud storage buckets add-iam-policy-binding gs://$BUCKET \
  --member="serviceAccount:sa-weather-cloudrun-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="roles/storage.objectCreator"

```

Acceso a BigQuery **solo en los datasets que escribe**, con DCL de BigQuery (en BigQuery Studio o con `bq query --use_legacy_sql=false`):
```sql
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-weth.raw_arl_pe_openmeteo`
  TO "serviceAccount:sa-weather-cloudrun-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com";

GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-weth.std_arl_pe_openmeteo`
  TO "serviceAccount:sa-weather-cloudrun-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com";
```
> `bq add-iam-policy-binding` a nivel de dataset devuelve `This feature requires allowlisting`; `GRANT ... ON SCHEMA` logra lo mismo sin esa limitación.

### 5.2.1. Permisos de `sa-weather-sq-runtime`
```bash
gcloud projects add-iam-policy-binding arl-dtpr-dev-weth \
  --member="serviceAccount:sa-weather-sq-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"
```
```sql
GRANT `roles/bigquery.dataViewer` ON SCHEMA `arl-dtpr-dev-weth.raw_arl_pe_openmeteo`
  TO "serviceAccount:sa-weather-sq-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-weth.std_arl_pe_openmeteo`
  TO "serviceAccount:sa-weather-sq-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com";
GRANT `roles/bigquery.dataEditor` ON SCHEMA `arl-dtpr-dev-weth.trf_weather`
  TO "serviceAccount:sa-weather-sq-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com";
```

### 5.2.2. Permiso de `sa-weather-cloudbuild`
```bash
gcloud projects add-iam-policy-binding arl-dtpr-dev-weth \
  --member="serviceAccount:sa-weather-cloudbuild@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="roles/run.builder"
```

### 5.2.3. Retirar `roles/editor` de la cuenta default de Compute
Solo después de validar el pipeline completo con las cuentas nuevas:
```bash
gcloud projects remove-iam-policy-binding arl-dtpr-dev-weth \
  --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
  --role="roles/editor"
```

### 5.3. Rol personalizado para disparar la Scheduled Query
```bash
gcloud iam roles create weatherTransferRunner --project=arl-dtpr-dev-weth \
  --title="Weather Transfer Runner" \
  --description="Permite disparar y consultar ejecuciones manuales de la Scheduled Query" \
  --permissions=bigquery.transfers.get,bigquery.transfers.update
```

### 5.4. Permisos de `sa-weather-workflow-runtime`
```bash
gcloud projects add-iam-policy-binding arl-dtpr-dev-weth \
  --member="serviceAccount:sa-weather-workflow-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="projects/arl-dtpr-dev-weth/roles/weatherTransferRunner"

gcloud projects add-iam-policy-binding arl-dtpr-dev-weth \
  --member="serviceAccount:sa-weather-workflow-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="roles/logging.logWriter"
```
El permiso `roles/run.invoker` sobre el Cloud Run se otorga después de desplegarlo (sección 7.7).

### 5.5. Permiso de `sa-weather-scheduler-invoker`
```bash
gcloud projects add-iam-policy-binding arl-dtpr-dev-weth \
  --member="serviceAccount:sa-weather-scheduler-invoker@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="roles/workflows.invoker"
```

---

## 6. Capa de datos — detalle de cada objeto

### 6.1. Cloud Storage — zona raw
| Campo | Valor |
|---|---|
| Nombre | `raw-arl-weth-pe-openmeteo-dev-<SUFFIX>` |
| Región / clase | `us-central1` · Standard |
| Acceso | Privado, sin acceso público |
| Ruta de objetos | `weather_current/in/<YYYYMMDD>/weather_<LOCATION_ID>_<YYYYMMDDHHMMSS>.json` |
| Escrito por | `cr-consumo-openmeteo-api` (rol `storage.objectCreator`) |

**Qué hace:** conserva el JSON exacto que devolvió Open-Meteo, sin transformar, uno por ciudad y por ejecución. Sirve como fuente de verdad y permite reprocesar sin volver a llamar a la API. La ruta sigue la taxonomía de buckets raw: `<file_table_name>/in/<fecha>/<archivo_timestamp>`.

```bash
gcloud storage buckets create gs://raw-arl-weth-pe-openmeteo-dev-<SUFFIX> \
  --location=us-central1 --default-storage-class=STANDARD \
  --uniform-bucket-level-access --public-access-prevention \
  --project=arl-dtpr-dev-weth
```

### 6.2. BigQuery — `raw_arl_pe_openmeteo.current_weather` (capa raw)
Espejo de la fuente: mismos nombres de campo que devuelve Open-Meteo, sin validar. Particionada por `DATE(ingestion_timestamp)`, clusterizada por `location_id`.

| Columna | Tipo | Descripción |
|---|---|---|
| `location_id` | STRING NOT NULL | Código corto de la ciudad (LIM, AQP, TRU, CUS) |
| `location_name` | STRING NOT NULL | Nombre legible |
| `latitude` / `longitude` | FLOAT64 | Coordenadas en grados decimales |
| `time` | TIMESTAMP | Timestamp de la observación tal como lo devuelve la fuente |
| `temperature_2m` | FLOAT64 | Temperatura a 2 m (°C), nombre original de Open-Meteo |
| `relative_humidity_2m` | FLOAT64 | Humedad relativa a 2 m (%) |
| `wind_speed_10m` | FLOAT64 | Viento a 10 m (km/h) |
| `ingestion_timestamp` | TIMESTAMP NOT NULL | Momento UTC de ingesta; columna de partición |

### 6.3. BigQuery — `std_arl_pe_openmeteo.trx_weather_reading` (capa estandarizada)
Tabla transaccional: una lectura horaria validada por ciudad, con nombres estandarizados. Particionada por `DATE(ingestion_timestamp)`, clusterizada por `location_id`.

| Columna | Tipo | Descripción |
|---|---|---|
| `location_id` | STRING NOT NULL | FK hacia `ori_mtr_location.location_id` |
| `observed_at` | TIMESTAMP | Momento de la observación |
| `temperature_c` | FLOAT64 | Temperatura (°C) |
| `relative_humidity_pct` | FLOAT64 | Humedad relativa (%) |
| `wind_speed_kmh` | FLOAT64 | Viento (km/h) |
| `ingestion_timestamp` | TIMESTAMP NOT NULL | Momento UTC de ingesta; columna de partición |

**Regla de calidad aplicada antes de insertar** (`is_valid_record`): se descarta la fila si `observed_at` o `temperature_c` son nulos, o si la temperatura está fuera del rango `-90 °C … 60 °C`. Los descartes se cuentan en `rows_skipped`.

### 6.4. BigQuery — `std_arl_pe_openmeteo.ori_mtr_location` (maestro)
Maestro de datos propio del negocio: una fila por ciudad. **Se autopobla** desde la Scheduled Query mediante `MERGE ... WHEN NOT MATCHED`, por lo que es seguro truncarla para una prueba limpia.

| Columna | Tipo | Descripción |
|---|---|---|
| `location_id` | STRING NOT NULL | Llave primaria |
| `location_name` | STRING NOT NULL | Nombre de la ciudad |
| `latitude` / `longitude` | FLOAT64 | Coordenadas |
| `country` | STRING | Fijo en `'Peru'` al momento de la carga |

### 6.5. BigQuery — `trf_weather.trf_weather_hourly` (tabla de hechos curada)
Una fila por observación horaria por ubicación, cargada con `MERGE` para ser idempotente. Particionada por `DATE(observed_at)`, clusterizada por `location_id`. Es la tabla pensada para consumo (Looker Studio, análisis).

| Columna | Tipo | Descripción |
|---|---|---|
| `location_id` | STRING NOT NULL | FK hacia `ori_mtr_location` |
| `observed_at` | TIMESTAMP NOT NULL | Momento de la observación; columna de partición |
| `temperature_c` / `relative_humidity_pct` / `wind_speed_kmh` | FLOAT64 | Métricas |
| `ingestion_timestamp` | TIMESTAMP NOT NULL | Momento en que el registro fuente fue ingerido originalmente |

### 6.6. Creación de datasets y tablas
```bash
bq --location=US mk --dataset arl-dtpr-dev-weth:raw_arl_pe_openmeteo
bq --location=US mk --dataset arl-dtpr-dev-weth:std_arl_pe_openmeteo
bq --location=US mk --dataset arl-dtpr-dev-weth:trf_weather

bq query --use_legacy_sql=false < bigquery/raw_arl_pe_openmeteo/current_weather.sql
bq query --use_legacy_sql=false < bigquery/std_arl_pe_openmeteo/ori_mtr_location.sql
bq query --use_legacy_sql=false < bigquery/std_arl_pe_openmeteo/trx_weather_reading.sql
bq query --use_legacy_sql=false < bigquery/trf_weather/trf_weather_hourly.sql
```
> También se pueden pegar los DDL directamente en el editor de BigQuery Studio.

---

## 7. Cloud Run — `cr-consumo-openmeteo-api`

| Campo | Valor |
|---|---|
| Tipo | Servicio Cloud Run (no función), arquitectura en capas |
| Acceso | **Privado** (`--no-allow-unauthenticated`), requiere token de identidad |
| Identidad de ejecución | `sa-weather-cloudrun-runtime` |
| URL | `https://cr-consumo-openmeteo-api-<PROJECT_NUMBER>.us-central1.run.app` |
| Rutas | `GET/POST /` y `GET/POST /weather-ingest` |
| Tests | 20, todos pasando |

### 7.1. Estructura del código
```
cloud-run/cr-consumo-openmeteo-api/
├── Dockerfile · pyproject.toml · requirements.txt · .gcloudignore · .dockerignore
├── src/app/
│   ├── main.py                       # Flask + blueprint + /health
│   ├── api/routes/weather.py         # ruta HTTP; traduce errores a códigos HTTP
│   ├── core/config.py                # variables de entorno
│   ├── integrations/
│   │   ├── open_meteo/main.py        # cliente Open-Meteo + OpenMeteoError
│   │   ├── storage/main.py           # sube JSON crudo a GCS + StorageUploadError
│   │   └── bigquery/main.py          # inserta en raw y std + BigQueryInsertError
│   ├── services/weather_service.py   # orquesta fetch → subir crudo → limpiar → validar → insertar
│   └── utils/{common.py, logging.py}
└── tests/                            # conftest, test_common, test_open_meteo_integration, test_endpoints, test_weather_service
```

### 7.2. Qué hace cada módulo
- **`api/routes/weather.py`**: expone la ruta, escribe los banners de log (`INICIO/FIN CR CONSUMO OPENMETEO API`) y devuelve `{"status":"success","service":...,"payload":{...}}` con HTTP 200. Errores de Storage o BigQuery → HTTP **502** `Integration Error`; cualquier otro → HTTP **500** `Internal Error`.
- **`core/config.py`**: lee todas las variables de entorno. `GCS_BUCKET_NAME` es obligatoria y no tiene valor de respaldo: si falta, el servicio no arranca, para no escribir en un bucket equivocado.
- **`integrations/open_meteo/main.py`**: `fetch_weather(lat, lon, timeout=15)` llama a `api.open-meteo.com/v1/forecast` pidiendo `current` y `hourly` con `temperature_2m, relative_humidity_2m, wind_speed_10m` y `timezone=GMT`, para que las horas lleguen en UTC (BigQuery guarda un TIMESTAMP sin offset como UTC). Convierte fallos de red o JSON inválido en `OpenMeteoError`.
- **`integrations/storage/main.py`**: `upload_raw_payload()` sube el JSON sin transformar a `weather_current/in/<fecha>/weather_<ciudad>_<timestamp>.json`.
- **`integrations/bigquery/main.py`**: cliente reutilizado (singleton); `insert_raw_weather()` e `insert_standard_weather()` usan `insert_rows_json` y lanzan `BigQueryInsertError` si BigQuery devuelve errores.
- **`services/weather_service.py`**: contiene la lista de 4 ciudades y el flujo completo:
  1. Por cada ciudad, consulta Open-Meteo (si falla, la registra en `cities_failed` y continúa con las demás).
  2. Sube el JSON crudo a GCS.
  3. `build_raw_row()` arma la fila de la lectura actual y `build_hourly_raw_rows()` una fila por cada hora del pronóstico (~168).
  4. `clean_record()` estandariza nombres (`time→observed_at`, `temperature_2m→temperature_c`, etc.) y `is_valid_record()` filtra.
  5. Inserta todo en raw y std **antes** de responder, de modo que un 200 garantiza que los datos ya están en BigQuery.

### 7.3. Respuesta esperada
```json
{
  "status": "success",
  "service": "cr-consumo-openmeteo-api",
  "payload": {
    "cities_fetched": 4,
    "cities_failed": [],
    "rows_processed": 676,
    "rows_skipped": 0,
    "ingestion_timestamp": "2026-09-…"
  }
}
```

### 7.4. Variables de entorno

| Variable | Obligatoria | Default | Descripción |
|---|---|---|---|
| `GCS_BUCKET_NAME` | **Sí** | — | Bucket raw donde se sube el JSON crudo |
| `PROJECT_ID` | No | `arl-dtpr-dev-weth` | Proyecto de GCP (acepta también `GCP_PROJECT_ID`) |
| `SERVICE_NAME` | No | `cr-consumo-openmeteo-api` | Nombre para logs y respuestas |
| `BQ_RAW_DATASET` | No | `raw_arl_pe_openmeteo` | Dataset de la capa raw |
| `BQ_RAW_TABLE` | No | `current_weather` | Tabla de la capa raw |
| `BQ_STD_DATASET` | No | `std_arl_pe_openmeteo` | Dataset de la capa estandarizada |
| `BQ_STD_TABLE` | No | `trx_weather_reading` | Tabla de la capa estandarizada |

### 7.5. Pruebas antes de desplegar
```bash
cd cloud-run/cr-consumo-openmeteo-api
pip install -r requirements.txt pytest
GCS_BUCKET_NAME=test-bucket pytest tests/ -v
```

### 7.6. Despliegue
```bash
cd cloud-run/cr-consumo-openmeteo-api

gcloud run deploy cr-consumo-openmeteo-api \
  --source . \
  --region us-central1 \
  --no-allow-unauthenticated \
  --service-account=sa-weather-cloudrun-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com \
  --build-service-account=projects/arl-dtpr-dev-weth/serviceAccounts/sa-weather-cloudbuild@arl-dtpr-dev-weth.iam.gserviceaccount.com \
  --set-env-vars=PROJECT_ID=arl-dtpr-dev-weth,SERVICE_NAME=cr-consumo-openmeteo-api,GCS_BUCKET_NAME=raw-arl-weth-pe-openmeteo-dev-<SUFFIX>,BQ_RAW_DATASET=raw_arl_pe_openmeteo,BQ_RAW_TABLE=current_weather,BQ_STD_DATASET=std_arl_pe_openmeteo,BQ_STD_TABLE=trx_weather_reading
```

### 7.7. Permiso de invocación para el Workflow
```bash
gcloud run services add-iam-policy-binding cr-consumo-openmeteo-api \
  --region=us-central1 \
  --member="serviceAccount:sa-weather-workflow-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```
> Los permisos IAM tardan 1–2 minutos en propagarse. Un `403` justo después de otorgarlos se resuelve esperando y reintentando.

### 7.8. Prueba directa
```bash
curl -X POST https://cr-consumo-openmeteo-api-<PROJECT_NUMBER>.us-central1.run.app/ \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

---

## 8. BigQuery Scheduled Query — `sq_transform_weather_standard_to_trf`

| Campo | Valor |
|---|---|
| Modo | **On-demand** (no corre sola; la dispara el Workflow o "Run transfer now") |
| Identidad de ejecución | `sa-weather-sq-runtime` |
| Ubicación | `us` |
| SQL | `scheduled-query/sq_transform_weather_standard_to_trf.sql` |
| Config ID (transfer) | `<TRANSFER_CONFIG_ID>` |

**Qué hace, en 2 sentencias `MERGE` idempotentes:**
1. **Maestro de ciudades:** toma las ciudades distintas vistas en `raw_arl_pe_openmeteo.current_weather` (con nombre, latitud, longitud y país fijo `'Peru'`) y las inserta en `ori_mtr_location` solo si no existían (`WHEN NOT MATCHED`).
2. **Tabla curada:** toma de `trx_weather_reading` las lecturas del día (`DATE(ingestion_timestamp) = CURRENT_DATE()`) con `temperature_c` y `observed_at` no nulos, y las inserta en `trf_weather_hourly` solo si no existe ya esa pareja `(location_id, observed_at)`.

Al ser `MERGE ... WHEN NOT MATCHED`, se puede ejecutar N veces sin duplicar filas.

### 8.1. Creación (consola)
1. Pegar el SQL en el editor de BigQuery Studio y ejecutarlo una vez.
2. **Schedule → Create new scheduled query**, nombre `sq_transform_weather_standard_to_trf`.
3. Frecuencia **On-demand**, ubicación `us`, service account = `sa-weather-sq-runtime`.

> **Cuidado al editar la Scheduled Query desde la consola.** Al cambiar la service account en el panel **Edit**, el panel guarda también la sección *Schedule options*; en este proyecto quedó `Repeat frequency = Hours` y la query empezó a correr sola cada hora. Revisar siempre que **Repeat frequency** siga en **On-demand** antes de guardar. (En este proyecto, `bq update --transfer_config --service_account_name=...` informó éxito sin aplicar el cambio, por eso se usó la consola.)
4. Copiar el `transferConfigId` (se ve con `bq ls --transfer_config --transfer_location=us --project_id=arl-dtpr-dev-weth`); se usa en el Workflow.

---

## 9. Cloud Workflow — `orquestador-weather`

| Campo | Valor |
|---|---|
| Región | `us-central1` |
| Identidad | `sa-weather-workflow-runtime` |
| Definición | `workflow/orquestador-weather.yaml` |
| Variables de entorno | `workflow/env.yaml` |

### 9.1. Variables de entorno del Workflow (nada hardcodeado en el YAML)

| Variable | Valor |
|---|---|
| `project_id` | `arl-dtpr-dev-weth` |
| `project_number` | `<PROJECT_NUMBER>` |
| `region` | `us-central1` |
| `transfer_location` | `us` |
| `cloud_run_service_name` | `cr-consumo-openmeteo-api` |
| `transfer_config_id` | `<TRANSFER_CONFIG_ID>` |
| `poll_interval_seconds` | `10` |

### 9.2. Pasos del Workflow
| Paso | Qué hace |
|---|---|
| `init` | Lee las 7 variables con `sys.get_env()` y construye `cloud_run_url` y `transfer_config_name` |
| `call_cloud_run` | `http.post` con `auth: OIDC` dentro de `try/except`; si falla, levanta un error con el código HTTP y el body reales de Cloud Run |
| `log_cloud_run_result` | Registra la respuesta con `sys.log` |
| `check_cloud_run_status` | `switch`: si `body.status != "success"` levanta error (no basta con HTTP 200) |
| `trigger_scheduled_query` | Llama a `bigquerydatatransfer…transferConfigs.startManualRuns` |
| `extract_run_name` | Guarda el nombre de la ejecución devuelta |
| `check_transfer_run_status` → `evaluate_transfer_status` → `wait_before_retry` | Bucle de polling: consulta el estado cada `poll_interval_seconds`; `SUCCEEDED` → éxito, `FAILED`/`CANCELLED` → error con detalle |
| `workflow_success` | Devuelve `cloud_run_result` y `scheduled_query_final_state` |

### 9.3. Resultado esperado
```json
{
  "cloud_run_result": {"payload": {"cities_fetched": 4, "rows_processed": 676, "...": "..."}, "service": "cr-consumo-openmeteo-api", "status": "success"},
  "scheduled_query_final_state": "SUCCEEDED"
}
```

### 9.4. Creación (siempre por la consola)
El Workflow se crea con el asistente de la consola, no con `gcloud workflows deploy`:
1. **Workflows → Create**.
2. Completar nombre `orquestador-weather`, descripción, región `us-central1`, service account `sa-weather-workflow-runtime`.
3. En **Environment variables**, cargar las 7 variables de la sección 9.1.
4. **Next** → pegar el contenido de `orquestador-weather.yaml` → **Deploy**.

### 9.5. Ejecución (siempre con el botón Execute)
Workflows → `orquestador-weather` → **Execute** (entrada `{}`) → revisar la pestaña de la ejecución y el grafo de pasos.

> **Detalle importante de la URL:** `cloud_run_url` debe construirse **sin** barra final (`...run.app`). Una `/` sobrante provoca `403 Forbidden ... insufficient_scope` porque el *audience* del token OIDC no coincide con la URL del servicio.

---

## 10. Cloud Scheduler — `job-trigger-weather-ingest`

| Campo | Valor |
|---|---|
| Cron | `0 * * * *` (cada hora en punto) |
| Zona horaria | `America/Lima` |
| Destino | El Workflow `orquestador-weather` (no directamente el Cloud Run) |
| Autenticación | OAuth con `sa-weather-scheduler-invoker` |
| Estado | **Creado y PAUSADO** a propósito |

```bash
gcloud scheduler jobs create http job-trigger-weather-ingest \
  --location=us-central1 \
  --schedule="0 * * * *" --time-zone="America/Lima" \
  --uri="https://workflowexecutions.googleapis.com/v1/projects/arl-dtpr-dev-weth/locations/us-central1/workflows/orquestador-weather/executions" \
  --http-method=POST \
  --oauth-service-account-email=sa-weather-scheduler-invoker@arl-dtpr-dev-weth.iam.gserviceaccount.com

gcloud scheduler jobs pause job-trigger-weather-ingest --location=us-central1
```
Mientras esté `PAUSED` no se puede disparar ni manualmente (`FAILED_PRECONDITION`); la vía de prueba es el botón Execute del Workflow. Para automatizar: `gcloud scheduler jobs resume job-trigger-weather-ingest --location=us-central1`.

---

## 11. Checklist de verificación (capturas para el documento E2E)

- [ ] Workflow `orquestador-weather`: ejecución con estado `Succeeded`
- [ ] Cloud Run `cr-consumo-openmeteo-api`: logs con `INICIO … / FIN CR CONSUMO OPENMETEO API OK`
- [ ] Bucket `raw-arl-weth-pe-openmeteo-dev-…`: archivos JSON en `weather_current/in/<fecha>/`
- [ ] `raw_arl_pe_openmeteo.current_weather` con filas (≈ 676 por corrida)
- [ ] `std_arl_pe_openmeteo.trx_weather_reading` con filas validadas
- [ ] Scheduled Query `sq_transform_weather_standard_to_trf`: ejecución exitosa en el historial
- [ ] `std_arl_pe_openmeteo.ori_mtr_location` con 4 ciudades
- [ ] `trf_weather.trf_weather_hourly` con datos
- [ ] Cloud Scheduler `job-trigger-weather-ingest` visible (pausado)

### 11.1. Consulta de negocio de ejemplo
```sql
SELECT l.location_name,
       ROUND(AVG(h.temperature_c), 1) AS temp_promedio_c,
       ROUND(AVG(h.relative_humidity_pct), 1) AS humedad_promedio_pct
FROM `trf_weather.trf_weather_hourly` h
JOIN `std_arl_pe_openmeteo.ori_mtr_location` l USING (location_id)
GROUP BY l.location_name
ORDER BY temp_promedio_c DESC;
```

### 11.2. Prueba limpia (E2E desde cero)
```sql
TRUNCATE TABLE `raw_arl_pe_openmeteo.current_weather`;
TRUNCATE TABLE `std_arl_pe_openmeteo.trx_weather_reading`;
TRUNCATE TABLE `std_arl_pe_openmeteo.ori_mtr_location`;
TRUNCATE TABLE `trf_weather.trf_weather_hourly`;
```
Se usa `TRUNCATE`, nunca `DROP`: los pipelines repueblan las tablas en la siguiente ejecución. `ori_mtr_location` es seguro de truncar porque se autopobla en la Scheduled Query.

---

## 12. Resumen de variables por componente

| Componente | Variable | Ejemplo |
|---|---|---|
| Cloud Run | `GCS_BUCKET_NAME` (obligatoria) | `raw-arl-weth-pe-openmeteo-dev-<SUFFIX>` |
| Cloud Run | `PROJECT_ID` / `SERVICE_NAME` | `arl-dtpr-dev-weth` / `cr-consumo-openmeteo-api` |
| Cloud Run | `BQ_RAW_DATASET` / `BQ_RAW_TABLE` | `raw_arl_pe_openmeteo` / `current_weather` |
| Cloud Run | `BQ_STD_DATASET` / `BQ_STD_TABLE` | `std_arl_pe_openmeteo` / `trx_weather_reading` |
| Workflow | `project_id`, `project_number`, `region`, `transfer_location` | `arl-dtpr-dev-weth`, `<PROJECT_NUMBER>`, `us-central1`, `us` |
| Workflow | `cloud_run_service_name`, `transfer_config_id`, `poll_interval_seconds` | `cr-consumo-openmeteo-api`, `<TRANSFER_CONFIG_ID>`, `10` |

---

## 13. Problemas conocidos y cómo se resolvieron

| Síntoma | Causa | Solución |
|---|---|---|
| `403` al llamar a Cloud Run desde el Workflow justo tras otorgar `run.invoker` | Propagación de IAM (1–2 min) | Esperar y reintentar |
| `403 insufficient_scope` desde el Workflow | Barra final `/` en la URL → audience OIDC no coincide | Construir la URL sin `/` final |
| `Workflows service agent does not exist (Code: 9)` | API recién habilitada | `gcloud beta services identity create --service=workflows.googleapis.com` |
| "Cuenta no encontrada" persistente | Número de proyecto escrito con dos dígitos transpuestos | Verificar con `gcloud projects describe arl-dtpr-dev-weth --format="value(projectNumber)"` |
| `This feature requires allowlisting` en `bq add-iam-policy-binding` | Limitación de la herramienta a nivel dataset | Otorgar el acceso por dataset con DCL: `GRANT ... ON SCHEMA` |
| La Scheduled Query empezó a correr sola cada hora | Al cambiar la service account desde el panel **Edit** de la consola, se guardó también `Repeat frequency = Hours` | Volver **Repeat frequency** a **On-demand**; revisarlo siempre antes de guardar ese panel |
| `bq show --transfer_config` sigue mostrando la cuenta anterior tras el cambio | `ownerInfo.email` no refleja la identidad de ejecución | Verificar con `user_email` en `INFORMATION_SCHEMA.JOBS_BY_PROJECT` |
| Horas de `observed_at` corridas 5 h (ej. el pico de temperatura de Arequipa a las 13:00 "UTC") | Con `timezone=auto`, Open-Meteo devuelve la hora local de cada ciudad sin offset y BigQuery la guarda como UTC | Pedir `timezone=GMT`; truncar las 4 tablas y volver a ejecutar el Workflow |
| `gcloud scheduler jobs run` → `FAILED_PRECONDITION` | Job en estado `PAUSED` | Ejecutar el Workflow con el botón Execute |

---

## 14. Evolución frente a la versión 1 (`gcp-cloudrun-weather-etl`)

| Aspecto | v1 | v2 (`arl-dtpr-dev-weth`) |
|---|---|---|
| Nombres | `svc-weather-api-consumer`, `weather_dw` | Taxonomía completa: `cr-consumo-openmeteo-api`, `raw_/std_/trf_` |
| Capas de datos | Landing + dim + fact | raw → standard → transformed, con particionado y clustering |
| Acceso Cloud Run | `--allow-unauthenticated` | Privado, con identidad propia de mínimo privilegio |
| Orquestación | Cloud Scheduler encadenando pasos | Cloud Workflow con verificación de éxito y polling real |
| Código | `main.py` único | Capas `api/core/integrations/services/utils` + 19 tests |
| Configuración | Parcialmente en código | Todo por variables de entorno |

---

## 15. Orden recomendado de despliegue desde cero

1. Crear proyecto, habilitar APIs (sección 3).
2. Crear cuentas de servicio y rol personalizado (sección 5).
3. Crear bucket, datasets y tablas (sección 6).
4. Correr los tests y desplegar el Cloud Run (sección 7); otorgar `run.invoker`.
5. Crear la Scheduled Query y anotar su `transferConfigId` (sección 8).
6. Crear el Workflow desde la consola con sus variables (sección 9).
7. Ejecutar el Workflow con el botón **Execute** y completar el checklist (sección 11).
8. Crear el Cloud Scheduler en estado pausado (sección 10).
