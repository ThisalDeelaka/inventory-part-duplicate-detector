# Runtime Environment Variables

This project supports both the legacy scan engine and the redesigned deterministic engine. The redesigned engine is optional at runtime so existing behavior remains available.

## Engine Selection

```text
USE_REDESIGNED_ENGINE=false
```

Default: `false`

Set to `true` to enable the redesigned deterministic engine. The redesigned engine uses ERP-aware normalization, attribute extraction, candidate generation, local similarity scoring, deterministic guardrails, decision statuses, and business-readable explanations.

No LLM, paid AI API, or real IFS integration is enabled by this setting.

## Redesigned Result Mode

```text
REDESIGNED_RESULT_MODE=review
```

Default: `review`

Allowed values:

- `review`
- `all`

`review` mode persists review-ready statuses:

- `DUPLICATE_CANDIDATE`
- `POSSIBLE_DUPLICATE_REVIEW`
- `DATA_CONFLICT_REVIEW`
- `CROSS_SITE_STANDARDIZATION_CANDIDATE`
- `INSUFFICIENT_DATA`

`review` mode excludes noisy debug statuses by default:

- `RELATED_BUT_NOT_DUPLICATE`
- `UNIQUE_NO_MATCH`

`all` mode persists all generated statuses, including debug statuses. Use it for analysis, validation, and troubleshooting rather than normal demos.

## Explicit Status Override

```text
REDESIGNED_INCLUDE_STATUSES=
```

Default: empty

Optional comma-separated list. When non-empty, valid statuses in this list override the `REDESIGNED_RESULT_MODE` defaults.

Example:

```text
REDESIGNED_INCLUDE_STATUSES=DUPLICATE_CANDIDATE,RELATED_BUT_NOT_DUPLICATE
```

Invalid status names are ignored. If no valid statuses are provided, the normal mode defaults are used.

## Recommended Demo Runtime

```text
USE_REDESIGNED_ENGINE=true
REDESIGNED_RESULT_MODE=review
REDESIGNED_INCLUDE_STATUSES=
```

This keeps the UI focused on review-ready candidates while preserving explanations and evidence fields.

## Safe Production Default

```text
USE_REDESIGNED_ENGINE=false
REDESIGNED_RESULT_MODE=review
REDESIGNED_INCLUDE_STATUSES=
```

This preserves legacy behavior until the redesigned engine is validated with customer-specific historical decisions and governance requirements.

## Kubernetes

The base Kubernetes ConfigMap uses safe defaults:

```text
USE_REDESIGNED_ENGINE=false
REDESIGNED_RESULT_MODE=review
REDESIGNED_INCLUDE_STATUSES=
```

For a demo/dev overlay, set:

```text
USE_REDESIGNED_ENGINE=true
REDESIGNED_RESULT_MODE=review
REDESIGNED_INCLUDE_STATUSES=
```

Do not hardcode redesigned mode as the default for production manifests unless the deployment owner has completed validation and sign-off.
