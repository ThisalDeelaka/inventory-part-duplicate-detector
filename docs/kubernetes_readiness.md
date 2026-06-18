# Kubernetes Readiness

The FastAPI service keeps scan logic mostly stateless and stores durable state through SQLAlchemy. Liveness uses `/health`; readiness uses `/ready`. Configuration is injected through a ConfigMap, while the example Secret contains future IFS placeholders only. CPU and memory requests/limits support scheduling and autoscaling decisions.

The sample backend intentionally uses one replica because SQLite on `emptyDir` is not shared and is therefore unsuitable for real multi-replica persistence. Use managed PostgreSQL and shared object storage before scaling replicas. Add a HorizontalPodAutoscaler after measuring CPU and latency. Long-running scans should eventually use a separately scalable background worker.

## Redesigned engine runtime flags

The base Kubernetes ConfigMap keeps the redesigned engine disabled by default:

```text
USE_REDESIGNED_ENGINE=false
REDESIGNED_RESULT_MODE=review
REDESIGNED_INCLUDE_STATUSES=
```

For a controlled demo/dev runtime, override the ConfigMap or use an overlay:

```text
USE_REDESIGNED_ENGINE=true
REDESIGNED_RESULT_MODE=review
REDESIGNED_INCLUDE_STATUSES=
```

`review` mode is recommended for demos because it persists review-ready statuses and filters out debug-only statuses such as `RELATED_BUT_NOT_DUPLICATE` and `UNIQUE_NO_MATCH`. Use `REDESIGNED_RESULT_MODE=all` only for troubleshooting or model validation runs.

See `backend/docs/runtime_env.md` for the full runtime environment reference.
