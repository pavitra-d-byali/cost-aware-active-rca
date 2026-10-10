
import csv
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

METRICS_URL = "http://localhost:52578/metrics"
OUTPUT_FILE = Path("data/ad_metrics.csv")
INTERVAL_SECONDS = 10

SAMPLE_PATTERN = re.compile(
    r'^([a-zA-Z_:][a-zA-Z0-9_:]*)'
    r'(?:\{([^}]*)\})?\s+'
    r'([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|NaN|[+-]?Inf)$'
)


def parse_labels(label_text):
    """Parse labels from a Prometheus text-format sample."""
    labels = {}

    if not label_text:
        return labels

    for match in re.finditer(r'(\w+)="((?:\\.|[^"\\])*)"', label_text):
        labels[match.group(1)] = match.group(2)

    return labels


def collect_metrics():
    """Fetch ad-service metrics and return timestamped samples."""
    response = requests.get(METRICS_URL, timeout=5)
    response.raise_for_status()

    timestamp = datetime.now(timezone.utc).isoformat()
    samples = []

    for line in response.text.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        match = SAMPLE_PATTERN.match(line)
        if not match:
            continue

        metric_name, label_text, value = match.groups()

        if not metric_name.startswith("demo_ad_"):
            continue

        samples.append({
            "timestamp_utc": timestamp,
            "metric_name": metric_name,
            "labels": str(parse_labels(label_text)),
            "value": value,
        })

    return samples


def main():
    """Collect metrics periodically and append them to a CSV."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    file_exists = OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0

    with OUTPUT_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "timestamp_utc",
                "metric_name",
                "labels",
                "value",
            ],
        )

        if not file_exists:
            writer.writeheader()

        print(f"Source: {METRICS_URL}")
        print(f"Output: {OUTPUT_FILE.resolve()}")
        print(f"Interval: {INTERVAL_SECONDS} seconds")
        print("Press Ctrl+C to stop.")

        try:
            while True:
                try:
                    samples = collect_metrics()

                    writer.writerows(samples)
                    file.flush()

                    print(
                        f"{datetime.now().strftime('%H:%M:%S')} - "
                        f"Recorded {len(samples)} samples"
                    )

                except requests.RequestException as error:
                    print(f"Metrics request failed: {error}")

                time.sleep(INTERVAL_SECONDS)

        except KeyboardInterrupt:
            print("\nCollection stopped.")


if __name__ == "__main__":
    main()
