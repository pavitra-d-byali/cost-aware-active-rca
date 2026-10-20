
import json
import os
from pathlib import Path

import requests

OPENSEARCH_URL = os.getenv(
    "OPENSEARCH_URL",
    "http://localhost:59343",
)
INDEX = "otel-logs-2026-10-20"
OUTPUT_FILE = Path("data/logs.jsonl")
MAX_RECORDS = 100


def main():
    url = f"{OPENSEARCH_URL}/{INDEX}/_search"

    query = {
        "size": MAX_RECORDS,
        "sort": [{"@timestamp": {"order": "desc"}}],
        "query": {"match_all": {}},
        "_source": [
            "@timestamp",
            "body",
            "severity",
            "resource.service.name",
            "resource.service.criticality",
            "traceId",
            "spanId",
        ],
    }

    response = requests.post(url, json=query, timeout=15)
    response.raise_for_status()

    hits = response.json().get("hits", {}).get("hits", [])
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        for hit in hits:
            record = hit.get("_source", {})
            record["opensearch_index"] = hit.get("_index")
            record["opensearch_id"] = hit.get("_id")
            file.write(json.dumps(record) + "\n")

    print(f"Logs retrieved: {len(hits)}")
    print(f"Output: {OUTPUT_FILE.resolve()}")


if __name__ == "__main__":
    main()
