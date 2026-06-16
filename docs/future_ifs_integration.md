# Future IFS Integration

The current demo reads CSV only. It does not call IFS Cloud, use Projections or OAuth, access `inventory_part_tab`, or create lobby pages and event actions.

A future approved adapter can retrieve Inventory Part data through supported IFS Cloud APIs/Projections, map it to the same canonical fields, and call the existing validation and scoring service. A preventive flow could be:

```text
user creates inventory part -> duplicate API check -> ranked candidates returned -> warning shown -> user decides
```

The engine can run on Kubernetes. Production evolution should add PostgreSQL, a worker for long scans, observability, approved secrets management, and supervised calibration from reviewed feedback. Automatic merging should remain outside the service.
