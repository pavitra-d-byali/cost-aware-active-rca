# cost-aware-active-rca
Cost-Aware Active Evidence Acquisition for Reliable Root Cause Analysis in Distributed Microservice Systems

## Prometheus Evidence Collection

### Overview

The Prometheus Evidence Collector periodically queries Prometheus and stores timestamped telemetry measurements in a CSV file. It is part of the telemetry collection component for the research project, **Cost-Aware Active Evidence Acquisition for Reliable Root Cause Analysis in Distributed Microservice Systems**.

The collector uses PromQL queries to gather latency, slow-request, database, and RPC error evidence from the OpenTelemetry Demo.

### Prerequisites

- Python 3.11 or compatible version
- Docker Desktop
- OpenTelemetry Demo running with Prometheus accessible at `http://localhost:9090`
- Python dependency: `requests`

Install the dependency if required:

```powershell
python -m pip install requests
```

### Running the Collector

From the repository root, run:

```powershell
python .\src\telemetry\collectors\prometheus_collector.py
```

The collector queries Prometheus every 30 seconds and appends the returned measurements to:

`data/prometheus_evidence.csv`

Press `Ctrl+C` to stop collection.

### Evidence Collected

The collector currently gathers five evidence types:

| Evidence type | Description |
|---|---|
| `rpc_average_latency_seconds` | Average server-side RPC latency over a five-minute window |
| `rpc_p95_latency_seconds` | Estimated 95th-percentile server-side RPC latency |
| `slow_request_fraction_over_1s` | Estimated fraction of RPC requests taking longer than one second |
| `database_query_p95_seconds` | Estimated p95 latency for database query operations |
| `non_ok_rpc_rate_per_second` | Rate of RPC responses with a status other than `OK` |

The slow-request query excludes the known telemetry infrastructure services `jaeger` and `otelcol-contrib` so that application-level slow-request measurements are easier to interpret.

### CSV Schema

Each evidence record contains the following fields:

| Column | Description |
|---|---|
| `timestamp_utc` | UTC timestamp when the evidence snapshot was collected |
| `evidence_name` | Type of measurement |
| `service_name` | Service associated with the measurement |
| `operation` | RPC method or database operation, when available |
| `status_code` | RPC response status code, when available |
| `value` | Numeric measurement returned by Prometheus |
| `status` | Collection outcome: `ok`, `no_data`, or `query_error` |

### Error Handling

The collector checks Prometheus responses and records query failures in the CSV. Empty query results are recorded as `no_data`, while successful queries with returned series are recorded as `ok`.

A successful collection status indicates that the query succeeded; it does not indicate that the measured service is healthy.

### Limitations

- Measurements depend on Prometheus availability and the telemetry being exported successfully.
- Latency percentiles are estimated from Prometheus histogram buckets.
- Metrics are aggregate measurements over time windows and are not automatically correlated with individual distributed traces.
- The collector gathers evidence but does not yet implement cost-aware evidence selection, root-cause ranking, or automated root-cause identification.
- Generated CSV datasets are experimental outputs and are not included in the source-code commit by default.

### Research Role

This component provides the telemetry evidence collection foundation for subsequent RCA research. The collected measurements can be used to investigate anomalous services, compare latency and error signals, and support the future development and evaluation of a cost-aware evidence acquisition strategy.