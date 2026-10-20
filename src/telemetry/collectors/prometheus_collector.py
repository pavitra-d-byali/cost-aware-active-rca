
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

PROMETHEUS_URL = "http://localhost:9090"
OUTPUT_FILE = Path("data/prometheus_evidence.csv")
INTERVAL_SECONDS = 30
REQUEST_TIMEOUT = 10

QUERIES = {
    "rpc_average_latency_seconds": """
        sum by (service_name, rpc_method) (
            rate(rpc_server_call_duration_seconds_sum[5m])
        )
        /
        sum by (service_name, rpc_method) (
            rate(rpc_server_call_duration_seconds_count[5m])
        )
    """,
    "rpc_p95_latency_seconds": """
        histogram_quantile(
            0.95,
            sum by (le, service_name, rpc_method) (
                rate(rpc_server_call_duration_seconds_bucket[5m])
            )
        )
    """,
    "slow_request_fraction_over_1s": """
        1 -
        (
            sum by (service_name, rpc_method) (
                rate(
                    rpc_server_call_duration_seconds_bucket{
                        le="1",
                        service_name!~"jaeger|otelcol-contrib"
                    }[5m]
                )
            )
            /
            sum by (service_name, rpc_method) (
                rate(
                    rpc_server_call_duration_seconds_count{
                        service_name!~"jaeger|otelcol-contrib"
                    }[5m]
                )
            )
        )
    """,
    "database_query_p95_seconds": """
        histogram_quantile(
            0.95,
            sum by (le, service_name) (
                rate(
                    db_client_operation_duration_seconds_bucket{
                        db_operation_name="sql.conn.query"
                    }[5m]
                )
            )
        )
    """,
    "non_ok_rpc_rate_per_second": """
        sum by (
            service_name, rpc_method, rpc_response_status_code
        ) (
            rate(
                rpc_server_call_duration_seconds_count{
                    rpc_response_status_code=~".+",
                    rpc_response_status_code!="OK"
                }[5m]
            )
        )
    """,
    }


def query_prometheus(query):
    """Run an instant PromQL query and return its result vector."""
    response = requests.get(
        f"{PROMETHEUS_URL}/api/v1/query",
        params={"query": query},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    payload = response.json()

    if payload.get("status") != "success":
        raise RuntimeError(payload.get("error", "Prometheus query failed"))

    return payload["data"]["result"]


def collect_evidence():
    """Collect evidence measurements and preserve their labels."""
    collected_at = datetime.now(timezone.utc).isoformat()
    records = []

    for evidence_name, query in QUERIES.items():
        try:
            results = query_prometheus(query)

            if not results:
                records.append({
                    "timestamp_utc": collected_at,
                    "evidence_name": evidence_name,
                    "service_name": "",
                    "operation": "",
                    "status_code": "",
                    "value": "",
                    "status": "no_data",
                })
                continue

            for result in results:
                labels = result.get("metric", {})
                value = result.get("value", ["", ""])[1]

                records.append({
                    "timestamp_utc": collected_at,
                    "evidence_name": evidence_name,
                    "service_name": labels.get("service_name", ""),
                    "operation": (
                        labels.get("rpc_method")
                        or labels.get("db_operation_name")
                        or ""
                    ),
                    "status_code": labels.get(
                        "rpc_response_status_code", ""
                    ),
                    "value": value,
                    "status": "ok",
                })

        except (requests.RequestException, ValueError, RuntimeError) as error:
            print(f"[WARNING] {evidence_name}: {error}")
            records.append({
                "timestamp_utc": collected_at,
                "evidence_name": evidence_name,
                "service_name": "",
                "operation": "",
                "status_code": "",
                "value": "",
                "status": "query_error",
            })

    return records


def main():
    """Append periodic Prometheus evidence snapshots to CSV."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0

    fields = [
        "timestamp_utc",
        "evidence_name",
        "service_name",
        "operation",
        "status_code",
        "value",
        "status",
    ]

    print(f"Prometheus: {PROMETHEUS_URL}")
    print(f"CSV output: {OUTPUT_FILE.resolve()}")
    print(f"Collection interval: {INTERVAL_SECONDS} seconds")
    print("Press Ctrl+C to stop.")

    with OUTPUT_FILE.open(
        "a", newline="", encoding="utf-8"
    ) as file:
        writer = csv.DictWriter(file, fieldnames=fields)

        if not file_exists:
            writer.writeheader()

        try:
            while True:
                records = collect_evidence()
                writer.writerows(records)
                file.flush()

                successful = sum(
                    record["status"] == "ok" for record in records
                )
                no_data = sum(
                    record["status"] == "no_data" for record in records
                )
                errors = sum(
                    record["status"] == "query_error" for record in records
                )

                print(
                    f"{datetime.now().strftime('%H:%M:%S')} | "
                    f"rows={len(records)} | "
                    f"successful={successful} | "
                    f"no_data={no_data} | errors={errors}"
                )

                time.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nCollection stopped.")


if __name__ == "__main__":
    main()
