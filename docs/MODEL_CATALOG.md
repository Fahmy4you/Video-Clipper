# 9Router combo catalog

The backend reads GET /v1/models using the key in the root .env. Only entries owned by
combo are offered for highlight analysis. IDs are not hardcoded.

Catalog metadata is cached on disk for five minutes, keyed by endpoint and credential
fingerprint. The cache contains no API keys. Stale results remain visible while refresh
runs in the background; failed refreshes retain the previous complete catalog.
Concurrent requests share a refresh and a file lease prevents overlapping refreshes
across backend processes.

Opening Home, Settings, refreshing the catalog, and validating a project never send
generation prompts. Catalog access does not establish inference availability or remaining
provider quota. Real structured generation uses POST /v1/chat/completions and the selected
combo. 9Router handles its member providers and account fallback.

The existing /api/model-catalog and /api/models URLs expose the new catalog. Connection
status is available at /api/ai/status, while credential management is performed through
.env and the external 9Router dashboard.
