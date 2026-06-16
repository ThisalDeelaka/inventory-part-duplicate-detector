# Kubernetes Readiness

The FastAPI service keeps scan logic mostly stateless and stores durable state through SQLAlchemy. Liveness uses `/health`; readiness uses `/ready`. Configuration is injected through a ConfigMap, while the example Secret contains future IFS placeholders only. CPU and memory requests/limits support scheduling and autoscaling decisions.

The sample backend intentionally uses one replica because SQLite on `emptyDir` is not shared and is therefore unsuitable for real multi-replica persistence. Use managed PostgreSQL and shared object storage before scaling replicas. Add a HorizontalPodAutoscaler after measuring CPU and latency. Long-running scans should eventually use a separately scalable background worker.
