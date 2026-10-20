
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

JAEGER_URL = os.getenv(
    "JAEGER_API_URL",
    "http://localhost:59319/jaeger/ui/api/v3",
)
OUTPUT_FILE = Path("data/traces.jsonl")
POLL_INTERVAL_SECONDS = 60
LOOKBACK_MINUTES = 5
REQUEST_TIMEOUT_SECONDS = 15


def attribute_value(value):
    """Convert a Jaeger OpenTelemetry attribute into a Python value."""
    if not isinstance(value, dict):
        return value

    for key in (
        "stringValue",
        "intValue",
        "doubleValue",
        "boolValue",
        "bytesValue",
        "arrayValue",
        "kvlistValue",
    ):
        if key in value:
            return value[key]

    return value


def attributes_to_dict(attributes):
    return {
        item["key"]: attribute_value(item.get("value", {}))
        for item in attributes or []
        if "key" in item
    }


def get_service_name(resource_attributes):
    attributes = attributes_to_dict(resource_attributes)
    return attributes.get("service.name", "unknown")


def fetch_traces(start_time, end_time):
    params = {
        "query.startTimeMin": start_time.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
        "query.startTimeMax": end_time.isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z"),
        "query.limit": 100,
    }

    response = requests.get(
        f"{JAEGER_URL}/traces",
        params=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def extract_spans(payload):
    result = payload.get("result", payload)
    resource_spans = result.get("resourceSpans", [])

    for resource_group in resource_spans:
        service_name = get_service_name(
            resource_group.get("resource", {}).get("attributes", [])
        )

        for scope_group in resource_group.get("scopeSpans", []):
            scope = scope_group.get("scope", {})

            for span in scope_group.get("spans", []):
                start_ns = int(span.get("startTimeUnixNano", "0"))
                end_ns = int(span.get("endTimeUnixNano", "0"))

                yield {
                    "trace_id": span.get("traceId"),
                    "span_id": span.get("spanId"),
                    "parent_span_id": span.get("parentSpanId") or None,
                    "service_name": service_name,
                    "operation_name": span.get("name"),
                    "kind": span.get("kind"),
                    "start_time_unix_nano": start_ns,
                    "end_time_unix_nano": end_ns,
                    "duration_ms": (
                        (end_ns - start_ns) / 1_000_000
                        if end_ns >= start_ns
                        else None
                    ),
                    "status": span.get("status", {}),
                    "attributes": attributes_to_dict(
                        span.get("attributes", [])
                    ),
                    "scope": scope,
                    "events": span.get("events", []),
                    "links": span.get("links", []),
                    "exported_at_utc": datetime.now(
                        timezone.utc
                    ).isoformat(),
                }


def append_new_spans(spans):
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    # Read existing identities so overlapping polling windows
    # don't repeatedly append the same span.
    existing = set()

    if OUTPUT_FILE.exists():
        with OUTPUT_FILE.open("r", encoding="utf-8") as file:
            for line in file:
                try:
                    item = json.loads(line)
                    existing.add(
                        (item.get("trace_id"), item.get("span_id"))
                    )
                except json.JSONDecodeError:
                    continue

    added = 0

    with OUTPUT_FILE.open("a", encoding="utf-8") as file:
        for span in spans:
            identity = (span.get("trace_id"), span.get("span_id"))

            if not all(identity) or identity in existing:
                continue

            file.write(json.dumps(span, ensure_ascii=False) + "\n")
            existing.add(identity)
            added += 1

    return added


def main():
    print(f"Jaeger API: {JAEGER_URL}")
    print(f"Output file: {OUTPUT_FILE.resolve()}")
    print("Polling for new spans. Press Ctrl+C to stop.")

    while True:
        try:
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(
                minutes=LOOKBACK_MINUTES
            )

            payload = fetch_traces(start_time, end_time)
            spans = list(extract_spans(payload))
            added = append_new_spans(spans)

            print(
                f"{datetime.now(timezone.utc).isoformat()} | "
                f"fetched={len(spans)} | new={added}"
            )

        except requests.RequestException as exc:
            print(f"Jaeger request error: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            print(f"Trace parsing error: {exc}")

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
