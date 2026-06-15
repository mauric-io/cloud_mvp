#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from datetime import datetime
from pathlib import Path
import argparse
import json
import shutil

import pandas as pd


ROOT = Path("/Users/mauricio/news_engine_tools")
DAILY = ROOT / "selector_lab/daily"
DATED = ROOT / "cloud_mvp/data/daily_selector_dates"
CURRENT = ROOT / "cloud_mvp/data/daily_selector_current"
NEEDED = [
    "daily_issue_clusters.csv",
    "daily_ranked_articles.csv",
    "daily_llm_candidate_packet.md",
    "daily_selector_report.md",
]


def latest_complete_source():
    candidates = sorted(
        (p for p in DAILY.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    ) if DAILY.exists() else []
    return next((p for p in candidates if all((p / name).is_file() for name in NEEDED)), None)


def url_set(path):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "url" not in df.columns:
        raise SystemExit(f"Missing url column: {path}")
    return {value.strip() for value in df["url"] if value.strip()}


def validate_source(src, requested_date):
    if not src.is_dir():
        raise SystemExit(f"Missing selector output for requested date: {src}")
    missing = [str(src / name) for name in NEEDED if not (src / name).is_file()]
    if missing:
        raise SystemExit(f"Requested date output is incomplete: {missing}")
    if src.name != requested_date:
        raise SystemExit(f"Source date mismatch: requested {requested_date}, found {src.name}")


def write_payload(src, dest, payload_date):
    dest.mkdir(parents=True, exist_ok=True)
    for name in NEEDED:
        shutil.copy2(src / name, dest / name)
    manifest = {
        "published_at": datetime.now().isoformat(timespec="seconds"),
        "date": payload_date,
        "source_dir": str(src),
        "payload_dir": str(dest),
        "copied": NEEDED,
    }
    (dest / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def reject_duplicate_date(payload_date, ranked_path):
    requested_urls = url_set(ranked_path)
    for other in sorted(DATED.iterdir()) if DATED.exists() else []:
        other_ranked = other / "daily_ranked_articles.csv"
        if other.name == payload_date or not other_ranked.is_file():
            continue
        if requested_urls == url_set(other_ranked):
            raise SystemExit(
                f"Refusing duplicate payload: {payload_date} and {other.name} "
                "have identical URL sets."
            )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="Exact YYYY-MM-DD selector date to publish.")
    args = ap.parse_args()

    src = DAILY / args.date
    validate_source(src, args.date)

    dated_dest = DATED / args.date
    write_payload(src, dated_dest, args.date)
    reject_duplicate_date(args.date, dated_dest / "daily_ranked_articles.csv")

    latest = latest_complete_source()
    if latest is None:
        raise SystemExit("No complete selector output exists for daily_selector_current.")
    write_payload(latest, CURRENT, latest.name)

    current_manifest = json.loads((CURRENT / "manifest.json").read_text(encoding="utf-8"))
    if current_manifest.get("date") != latest.name:
        raise SystemExit("Current manifest date does not match latest payload date.")

    print("PUBLISHED")
    print("DATED", dated_dest)
    print("CURRENT", CURRENT)
    print("CURRENT_DATE", latest.name)


if __name__ == "__main__":
    main()
