# Cuentas de servicio — `arl-dtpr-dev-weth`

Registro de todas las cuentas de servicio (service accounts) que existen y se
usan activamente en este proyecto, para qué sirve cada una, y qué permisos
tiene exactamente.

> Número de proyecto: `<PROJECT_NUMBER>` (se obtiene con
> `gcloud projects describe arl-dtpr-dev-weth --format="value(projectNumber)"`).

---

## 1. `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com`

**Nombre:** Default compute service account (cuenta autogenerada por GCP)

**Cómo se creó:** automáticamente, al habilitar la API de Compute Engine
(`compute.googleapis.com`) en el proyecto. No la creamos nosotros a propósito.

**Estado actual (tras el hardening de IAM): sin uso y sin permisos de proyecto.**
Ya no la usa ningún componente del pipeline:
- **Cloud Build** usa `sa-weather-cloudbuild` (`--build-service-account` en el deploy).
- La **BigQuery Scheduled Query** (`sq_transform_weather_standard_to_trf`) corre como `sa-weather-sq-runtime`.

**Permisos que tiene:**
| Rol | Alcance | Origen |
|---|---|---|
| ~~`roles/editor`~~ | ~~Todo el proyecto~~ | Otorgado automáticamente por GCP al crearla. **Retirado** en el hardening; verificado sin errores en el Workflow y en el redespliegue del Cloud Run |
| `roles/run.invoker` | Servicio `cr-consumo-openmeteo-api` | Otorgado durante la configuración inicial del Cloud Scheduler — **redundante** desde que existe `sa-weather-scheduler-invoker` |

**Nota:** GCP usaría esta cuenta por defecto en cualquier servicio nuevo
creado sin indicar cuenta (Cloud Run sin `--service-account`, Cloud Functions
gen2, VMs). Al agregar componentes, indicar siempre su cuenta de forma
explícita.

**Pendiente de limpieza (opcional):** quitarle el `roles/run.invoker`
redundante:
```bash
gcloud run services remove-iam-policy-binding cr-consumo-openmeteo-api \
  --region=us-central1 \
  --member="serviceAccount:<PROJECT_NUMBER>-compute@developer.gserviceaccount.com" \
  --role="roles/run.invoker"
```

---

## 2. `sa-weather-scheduler-invoker@arl-dtpr-dev-weth.iam.gserviceaccount.com`

**Nombre:** `sa-weather-scheduler-invoker`

**Cómo se creó:** explícitamente, a propósito, con:
```bash
gcloud iam service-accounts create sa-weather-scheduler-invoker \
  --display-name="Scheduler invoker for weather Workflow"
```

**Para qué se usa:** es la **única** identidad que usa el job de
**Cloud Scheduler** (`job-trigger-weather-ingest`) para disparar el Workflow
`orquestador-weather`, mediante un `POST` a la API de Workflow Executions
autenticado con OAuth (`--oauth-service-account-email`). El Scheduler ya no
llama al Cloud Run directamente: eso lo hace el Workflow.

**Permisos que tiene:**
| Rol | Alcance | Origen |
|---|---|---|
| `roles/workflows.invoker` | Proyecto | Otorgado explícitamente por nosotros |

**Por qué solo tiene ese permiso:** esta cuenta no ejecuta código propio;
solo inicia una ejecución del Workflow. No necesita tocar Cloud Run, BigQuery
ni Cloud Storage: esos permisos son de la identidad del Workflow y de la del
Cloud Run.

---

## 3. `sa-weather-cloudrun-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com`

**Nombre:** `sa-weather-cloudrun-runtime`

**Cómo se creó:** explícitamente, a propósito, con:
```bash
gcloud iam service-accounts create sa-weather-cloudrun-runtime \
  --display-name="Runtime identity for cr-consumo-openmeteo-api"
```

**Para qué se usa:** es la identidad con la que **corre el propio Cloud Run**
`cr-consumo-openmeteo-api` (configurada con `gcloud run services update
... --service-account=...`), reemplazando a la cuenta de Compute Engine por
defecto que usaba antes. Es la cuenta que ejecuta el código real: sube el
JSON crudo a GCS e inserta filas en BigQuery en cada request.

**Permisos que tiene:**
| Rol | Alcance | Origen |
|---|---|---|
| `roles/storage.objectCreator` | Solo el bucket `raw-arl-weth-pe-openmeteo-dev-<SUFFIX>` | Otorgado explícitamente por nosotros — acotado a ese bucket únicamente |
| `roles/bigquery.dataEditor` | Datasets `raw_arl_pe_openmeteo` y `std_arl_pe_openmeteo` únicamente | Otorgado con DCL de BigQuery (`GRANT ... ON SCHEMA`). Se retiró el permiso que tenía a nivel de proyecto |

**Nota sobre el alcance de BigQuery (resuelto):** originalmente se otorgó
`bigquery.dataEditor` a nivel de proyecto porque `bq add-iam-policy-binding`
a nivel de dataset devolvía `This feature requires allowlisting`. Se resolvió
con `GRANT ... ON SCHEMA`, que no requiere ese allowlisting. Hoy la cuenta solo
escribe en los 2 datasets que el código realmente toca, y no tiene ningún rol
a nivel de proyecto. Los `GRANT` son SQL: se ejecutan en BigQuery Studio o con
`bq query --use_legacy_sql=false`, no se pegan en la terminal.

---

## 4. `sa-weather-sq-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com`

**Nombre:** `sa-weather-sq-runtime` (creada en el hardening de IAM)

**Para qué se usa:** identidad de ejecución de la BigQuery Scheduled Query
`sq_transform_weather_standard_to_trf`. Se configura en la consola (Edit →
Schedule → Update scheduled query → Service account). No se cambió con
`bq update --service_account_name`: reportó éxito sin aplicar el cambio.

**Permisos que tiene:**
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/bigquery.jobUser` | Proyecto | Poder ejecutar la query |
| `roles/bigquery.dataViewer` | Dataset `raw_arl_pe_openmeteo` | Leer la capa raw (`current_weather`) |
| `roles/bigquery.dataEditor` | Datasets `std_arl_pe_openmeteo` y `trf_weather` | Escribir `ori_mtr_location` y `trf_weather_hourly` |

**Cuidado al guardar:** ese panel también trae **Schedule options**. Al
guardarlo sin revisarlo se activó `Repeat frequency = Hours, cada 1 hora` y la
query empezó a correr sola. Antes de **Save**, dejar **Repeat frequency =
On-demand**.

**Verificación:** el campo `user_email` del job `scheduled_query_<id>` en
`INFORMATION_SCHEMA.JOBS_BY_PROJECT` es esta cuenta. El `transfer_config_id`
no cambió, por lo que el Workflow no se modificó.

---

## 5. `sa-weather-cloudbuild@arl-dtpr-dev-weth.iam.gserviceaccount.com`

**Nombre:** `sa-weather-cloudbuild` (creada en el hardening de IAM)

**Para qué se usa:** identidad de **Cloud Build** al desplegar el Cloud Run
con `gcloud run deploy --source .`, indicada con
`--build-service-account=projects/arl-dtpr-dev-weth/serviceAccounts/sa-weather-cloudbuild@arl-dtpr-dev-weth.iam.gserviceaccount.com`.

**Permisos que tiene:**
| Rol | Alcance | Para qué |
|---|---|---|
| `roles/run.builder` | Proyecto | Leer el código subido, escribir la imagen en Artifact Registry y escribir los logs del build |

**Verificación:** `gcloud builds describe <ID> --region=us-central1 --format="value(serviceAccount)"`.

---

## 6. `sa-weather-workflow-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com`

**Para qué se usa:** identidad del Workflow `orquestador-weather`.

**Permisos que tiene:** `roles/run.invoker` sobre `cr-consumo-openmeteo-api`,
rol personalizado `weatherTransferRunner` (solo `bigquery.transfers.get` y
`bigquery.transfers.update`) y `roles/logging.logWriter`.

---

## Resumen

| Cuenta | Tipo | Usada por | Permiso principal |
|---|---|---|---|
| `<PROJECT_NUMBER>-compute@developer.gserviceaccount.com` | Automática (default) | **Ningún componente** | Sin `roles/editor` (retirado); solo queda un `run.invoker` redundante |
| `sa-weather-scheduler-invoker@arl-dtpr-dev-weth.iam.gserviceaccount.com` | Creada a propósito | Cloud Scheduler | `workflows.invoker` |
| `sa-weather-cloudrun-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com` | Creada a propósito | Runtime del Cloud Run `cr-consumo-openmeteo-api` | `storage.objectCreator` (1 bucket) + `bigquery.dataEditor` (solo `raw_` y `std_`) |
| `sa-weather-sq-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com` | Creada a propósito (hardening) | Scheduled Query `sq_transform_weather_standard_to_trf` | `bigquery.jobUser` + `dataViewer` en `raw_` + `dataEditor` en `std_` y `trf_` |
| `sa-weather-cloudbuild@arl-dtpr-dev-weth.iam.gserviceaccount.com` | Creada a propósito (hardening) | Cloud Build (deploy del Cloud Run) | `run.builder` |
| `sa-weather-workflow-runtime@arl-dtpr-dev-weth.iam.gserviceaccount.com` | Creada a propósito | Workflow `orquestador-weather` | `run.invoker` + `weatherTransferRunner` + `logging.logWriter` |

## Nota histórica (para no repetir el error)

Durante la configuración se usó por error el número de proyecto con dos
dígitos transpuestos en varios comandos. Los errores persistentes de "cuenta
no encontrada" parecían un problema de propagación de IAM, pero en realidad
apuntaban a una cuenta inexistente. Antes de usar el número de proyecto en un
comando, obtenerlo siempre con `gcloud projects describe`.
