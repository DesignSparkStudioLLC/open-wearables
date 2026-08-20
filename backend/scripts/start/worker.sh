#!/bin/bash
set -e -x

# -E / --events: emit task-sent/started/succeeded/failed events so Flower's Prometheus
# metrics (flower_task_runtime_seconds, flower_events_total) are populated for Grafana.
uv run celery -A app.main:celery_app worker --loglevel=info --pool=threads -E -Q default,sdk_sync,garmin_sync,webhook_sync
