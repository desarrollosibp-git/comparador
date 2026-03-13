# Comparador de Registros (Matcher API)

Servicio de comparacion de registros para busqueda de coincidencias probabilisticas entre dos conjuntos de datos.

Este proyecto expone:
- un endpoint sincronico (`/match`) para pruebas y respuestas inmediatas;
- un flujo asincronico (`/jobs/match` + `/jobs/{job_id}`) para procesamiento robusto con cola;
- persistencia de jobs en SQLite con idempotencia;
- worker Celery sobre Redis para ejecutar comparaciones en segundo plano.

---

## Tabla de contenido

- [Arquitectura](#arquitectura)
- [Tecnologias](#tecnologias)
- [Estructura del proyecto](#estructura-del-proyecto)
- [Requisitos](#requisitos)
- [Configuracion](#configuracion)
- [Ejecucion con Docker Compose](#ejecucion-con-docker-compose)
- [Uso de la API](#uso-de-la-api)
  - [1) Match sincronico](#1-match-sincronico)
  - [2) Match asincronico](#2-match-asincronico)
- [Formato de datos](#formato-de-datos)
- [Variables de entorno](#variables-de-entorno)
- [Monitoreo y depuracion](#monitoreo-y-depuracion)
- [Problemas comunes](#problemas-comunes)

---

## Arquitectura

Flujo simplificado:

1. Cliente envia payload de comparacion.
2. API FastAPI valida entrada.
3. En modo async:
   - crea job en SQLite (`matcher_jobs`);
   - encola tarea Celery (`matcher.run_match_job`);
   - worker procesa y actualiza estatus/progreso;
   - cliente consulta estatus por `job_id`.

Componentes:
- **FastAPI**: expone endpoints HTTP.
- **Celery**: ejecuta jobs de match en background.
- **Redis**: broker/backend de Celery.
- **SQLite**: almacenamiento de jobs e idempotencia.
- **recordlinkage/pandas**: motor de comparacion.

---

## Tecnologias

- Python 3.11
- FastAPI + Uvicorn
- Celery + Redis
- SQLite
- pandas
- recordlinkage
- rapidfuzz
- Docker + Docker Compose

---

## Estructura del proyecto

```text
comparador/
├─ app/
│  ├─ main.py         # API FastAPI (sync + async)
│  ├─ matcher.py      # Logica de comparacion
│  ├─ celery_app.py   # Configuracion Celery
│  ├─ tasks.py        # Tareas async
│  └─ job_store.py    # Persistencia SQLite de jobs
├─ docker-compose.yml
├─ Dockerfile
├─ requirements.txt
└─ .env.example
```

---

## Requisitos

- Docker Desktop (o Docker Engine + Compose)
- Puerto `8002` libre (API)
- Puerto `6379` libre (Redis)

---

## Configuracion

1. Copia variables de ejemplo:

```bash
cp .env.example .env
```

2. Ajusta al menos:
- `MATCHER_JOB_TOKEN` (recomendado para proteger endpoints async)
- `MATCHER_JOBS_DB_PATH` (ruta SQLite dentro del contenedor)

---

## Ejecucion con Docker Compose

Levantar servicios:

```bash
docker compose up --build -d
```

Ver estado:

```bash
docker compose ps
```

Ver logs:

```bash
docker compose logs -f matcher-api matcher-worker
```

Detener:

```bash
docker compose down
```

---

## Uso de la API

Base URL local:

`http://localhost:8002`

### 1) Match sincronico

Endpoint:

- `POST /match`

Uso recomendado:
- pruebas rapidas;
- casos de baja carga;
- debugging directo del motor de comparacion.

Ejemplo:

```bash
curl -X POST "http://localhost:8002/match" \
  -H "Content-Type: application/json" \
  -d '{
    "dataA": [
      {
        "curp": "AAAA000101HJCXXX00",
        "nombre": "JUAN PEREZ LOPEZ",
        "fecha_nacimiento": "1/1/2000"
      }
    ],
    "dataB": [
      {
        "curp": "AAAA000101HJCXXX00",
        "nombre": "JUAN PEREZ LOPEZ",
        "fecha_nacimiento": "1/1/2000"
      }
    ],
    "config": {
      "weights": {
        "curp": 0.55,
        "nombre": 0.25,
        "fecha_nacimiento": 0.20
      }
    }
  }'
```

Respuesta:
- lista `results` con `curp_score`, `nombre_score`, `fecha_nacimiento_score`, `score_final`.

### 2) Match asincronico

#### Crear job

- `POST /jobs/match`
- Requiere header `Idempotency-Key`.
- Si `MATCHER_JOB_TOKEN` esta configurado, requiere `Authorization: Bearer <token>`.

Ejemplo:

```bash
curl -X POST "http://localhost:2/jobs/match" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: req-12345" \
  -H "X-Request-Id: req-12345" \
  -H "X-Trace-Id: trace-abc-001" \
  -H "Authorization: Bearer TU_TOKEN" \
  -d '{
    "dataA": [{"curp":"AAAA000101HJCXXX00","nombre":"JUAN PEREZ","fecha_nacimiento":"1/1/2000"}],
    "dataB": [{"curp":"AAAA000101HJCXXX00","nombre":"JUAN PEREZ","fecha_nacimiento":"1/1/2000"}],
    "config": {"weights":{"curp":0.55,"nombre":0.25,"fecha_nacimiento":0.20}}
  }'
```

Respuesta:

```json
{
  "job_id": "job_xxx",
  "status": "PENDING",
  "trace_id": "trace-abc-001"
}
```

#### Consultar job

- `GET /jobs/{job_id}`

Ejemplo:

```bash
curl -X GET "http://localhost:8002/jobs/job_xxx" \
  -H "Authorization: Bearer TU_TOKEN"
```

Estados esperados:
- `PENDING`
- `PROCESSING`
- `DONE`
- `FAILED`

Respuesta incluye:
- `progress`
- `attempts`
- `result` (cuando termina en `DONE`)
- `error` (si falla)

---

## Formato de datos

Campos principales por registro:
- `curp`
- `nombre`
- `fecha_nacimiento`

El sistema normaliza:
- CURP: mayusculas y caracteres alfanumericos;
- nombre: lowercase/trim;
- fecha_nacimiento: comparacion exacta del valor normalizado recibido.

Puntajes:
- `curp_score`: coincidencia exacta (0 o 1).
- `fecha_nacimiento_score`: coincidencia exacta (0 o 1).
- `nombre_score`: similitud `jarowinkler`.
- `score_final`: suma ponderada por `weights`.

Si no se envian pesos validos, se usan defaults:
- `curp=0.55`
- `nombre=0.25`
- `fecha_nacimiento=0.20`

---

## Variables de entorno

Variables soportadas (ver `.env.example`):

- `MATCHER_JOB_TOKEN`
- `MATCHER_JOBS_DB_PATH`
- `CELERY_BROKER_URL`
- `CELERY_RESULT_BACKEND`
- `MATCHER_TASK_MAX_RETRIES`
- `MATCHER_TASK_RETRY_BASE_SECONDS`
- `MATCHER_TASK_TIME_LIMIT`
- `MATCHER_TASK_SOFT_TIME_LIMIT`

---

## Monitoreo y depuracion

Comandos utiles:

```bash
docker compose ps
docker compose logs -f matcher-api matcher-worker
docker compose logs --tail 200 matcher-worker
```

Validaciones basicas:
- API viva en `http://localhost:8002/docs`
- Redis healthy
- Worker con tarea registrada:
  - debe aparecer `matcher.run_match_job` en logs de arranque de Celery.

---

## Problemas comunes

### 1) `Received unregistered task of type 'matcher.run_match_job'`

Causa:
- worker Celery no cargo el modulo de tareas.

Accion:
- confirmar configuracion de Celery con inclusion de `tasks`;
- reconstruir y reiniciar contenedores:

```bash
docker compose up --build -d
```

### 2) Jobs siempre en `PENDING`/`PROCESSING`

Revisar:
- worker activo;
- conexion Redis;
- logs de `matcher-worker`;
- idempotency key repetida (puede devolver job existente).

### 3) `401 Token requerido` o `Token invalido`

Revisar:
- header `Authorization: Bearer ...`;
- valor de `MATCHER_JOB_TOKEN` en API y cliente.

---

## Notas de integracion

Este servicio esta pensado para integrarse con un backend orquestador (por ejemplo Laravel), que:
- construye `dataA` y `dataB`,
- dispara jobs async,
- hace polling de estatus,
- aplica reglas de negocio finales sobre los resultados del matcher.

---

## Licencia

Uso interno del proyecto.

