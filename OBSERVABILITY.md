# Local observability & MinIO

Local-only stack for watching the backend (FastAPI) and Celery in Grafana, plus a
MinIO S3 that satisfies the `RAW_PAYLOAD_STORAGE=s3` config. Nothing here is wired
into any deployed environment.

## What this adds

- **MinIO** (in the main `docker-compose.yml`) - S3-compatible storage for raw payloads,
  with a one-shot job that creates the `raw-payloads` and `open-wearables` buckets.
- **Prometheus + Grafana + redis-exporter** (in `docker-compose.observability.yml`) -
  metrics scraping and a ready-made dashboard.
- `/metrics` on the FastAPI app (`prometheus-fastapi-instrumentator`).
- Celery worker started with `-E` so Flower emits per-task Prometheus metrics.

## Prerequisites

MinIO expects these in `backend/config/.env` (endpoints use the compose service name):

```
RAW_PAYLOAD_STORAGE=s3
RAW_PAYLOAD_S3_BUCKET=raw-payloads
RAW_PAYLOAD_S3_ENDPOINT_URL=http://minio:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
AWS_ENDPOINT_URL=http://minio:9000
AWS_BUCKET_NAME=open-wearables
```

## Run

The backend image gains a new dependency (`prometheus-fastapi-instrumentator`) and the
worker start command changed, so rebuild on first run:

```bash
# main stack (incl. MinIO) + observability stack
docker compose -f docker-compose.yml -f docker-compose.observability.yml up -d --build
```

Just the main stack (MinIO included, no Grafana):

```bash
docker compose up -d --build
```

Confirm the MinIO buckets were created:

```bash
docker logs minio-createbuckets__open-wearables   # ends with "buckets ready"
```

## Access

| Service          | URL                    | Notes                                  |
|------------------|------------------------|----------------------------------------|
| Grafana          | http://localhost:3001  | `admin` / `admin`; dashboard auto-loads |
| Prometheus       | http://localhost:9090  | `Status → Targets` should be all `UP`   |
| MinIO console    | http://localhost:9001  | `minioadmin` / `minioadmin`             |
| MinIO S3 API     | http://localhost:9000  | used as `http://minio:9000` in-cluster  |
| Flower           | http://localhost:5555  | Celery task browser + `/metrics`        |

The dashboard **"Open Wearables - Backend & Celery"** has three sections:

- **Redis / Broker** - memory used vs `maxmemory`, used %, and per-queue depth
  (`sdk_sync`, `default`, `garmin_sync`, `webhook_sync`, `unacked`).
- **FastAPI** - request rate, p95 latency, and 4xx/5xx error rate per handler.
- **Celery** - task runtime p95 per task, event rate by type, and in-flight tasks.

## Ports

Override via env vars if any clash locally:
`GRAFANA_PORT` (3001), `PROMETHEUS_PORT` (9090), `REDIS_EXPORTER_PORT` (9121),
`MINIO_PORT` (9000), `MINIO_CONSOLE_PORT` (9001).

## Notes

- Grafana runs on **3001** because the frontend already uses 3000.
- The observability compose file is separate - omit `-f docker-compose.observability.yml`
  to run without it. The `/metrics` endpoint and the worker `-E` flag are harmless when
  nothing is scraping them.
- Metric names in the Celery panels come from Flower/redis-exporter and can vary slightly
  by version. If a panel is empty, check the raw metric names and adjust the query:
  ```bash
  curl -s localhost:5555/metrics | grep flower_
  curl -s localhost:9121/metrics | grep redis_key_size
  ```
  The dashboard is editable in Grafana (`allowUiUpdates: true`).
- Running the backend **outside** Docker (bare `uv run`)? Point the S3/AWS endpoints at
  `http://localhost:9000` instead of `http://minio:9000`.
