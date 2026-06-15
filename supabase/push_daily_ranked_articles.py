#!/usr/bin/env python3
import argparse
import json
import os
import sys
from pathlib import Path

import pandas as pd
import requests


ROOT = Path("/Users/mauricio/news_engine_tools")


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing env var: {name}")
    return value


def headers(service_key: str) -> dict:
    return {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=representation",
    }


def parse_json_cell(value, default):
    if pd.isna(value) or str(value).strip() == "":
        return default

    text = str(value).strip()

    try:
        return json.loads(text)
    except Exception:
        if isinstance(default, list):
            return [x.strip() for x in text.split(",") if x.strip()]
        return {"raw": text}


def upsert(base_url: str, service_key: str, table: str, rows: list[dict], conflict: str):
    r = requests.post(
        f"{base_url}/rest/v1/{table}",
        headers=headers(service_key),
        params={"on_conflict": conflict},
        data=json.dumps(rows, ensure_ascii=False),
        timeout=90,
    )

    if r.status_code not in (200, 201, 204):
        print(r.text, file=sys.stderr)
        raise SystemExit(f"Upsert failed: table={table} status={r.status_code}")

    return r.json() if r.text else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--source", default="daily_selector")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    csv_path = ROOT / "cloud_mvp" / "data" / "daily_selector_dates" / args.date / "daily_ranked_articles.csv"

    if not csv_path.exists():
        raise SystemExit(f"Missing CSV: {csv_path}")

    df = pd.read_csv(csv_path)

    required = [
        "cluster_rank",
        "cluster_id",
        "article_score",
        "product",
        "outlet",
        "domain",
        "title",
        "url",
        "url_strong_tags",
        "url_weak_tags",
        "learned_scores_json",
        "learned_hits_json",
        "reasons",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Missing columns: {missing}")

    df = df[df["url"].notna() & df["title"].notna()].copy()
    df["url"] = df["url"].astype(str).str.strip()
    df = df[df["url"] != ""].copy()

    # Keep one row per product/url inside this dated selector file.
    df = df.drop_duplicates(subset=["product", "url"], keep="first").copy()

    base_url = env_required("SUPABASE_URL").rstrip("/")
    service_key = env_required("SUPABASE_SERVICE_ROLE_KEY")

    products = sorted(df["product"].dropna().astype(str).unique().tolist())

    if args.dry_run:
        print(f"csv={csv_path}")
        print(f"rows={len(df)}")
        print(f"products={products}")
        print("sample:")
        sample = df.iloc[0]
        print(json.dumps({
            "article_date": args.date,
            "product": str(sample["product"]),
            "outlet": sample["outlet"],
            "domain": sample["domain"],
            "title": sample["title"],
            "url": sample["url"],
            "cluster_rank": int(sample["cluster_rank"]),
            "cluster_id": str(sample["cluster_id"]),
            "relevance_score": float(sample["article_score"]),
            "url_strong_tags": parse_json_cell(sample["url_strong_tags"], []),
            "url_weak_tags": parse_json_cell(sample["url_weak_tags"], []),
            "learned_scores": parse_json_cell(sample["learned_scores_json"], {}),
            "learned_hits": parse_json_cell(sample["learned_hits_json"], {}),
            "selector_reasons": sample["reasons"],
        }, ensure_ascii=False, indent=2))
        return

    total_pushed = 0

    for product in products:
        part = df[df["product"].astype(str) == product].copy()

        run_rows = upsert(
            base_url,
            service_key,
            "runs",
            [{
                "run_date": args.date,
                "product": product,
                "source": args.source,
            }],
            "run_date,product,source",
        )

        if not run_rows:
            raise SystemExit(f"No run row returned for product={product}")

        run_id = run_rows[0]["id"]

        article_rows = []

        for _, row in part.iterrows():
            article_rows.append({
                "run_id": run_id,
                "article_date": args.date,
                "product": product,
                "outlet": None if pd.isna(row["outlet"]) else str(row["outlet"]),
                "domain": None if pd.isna(row["domain"]) else str(row["domain"]),
                "title": str(row["title"]),
                "url": str(row["url"]),
                "cluster_rank": None if pd.isna(row["cluster_rank"]) else int(row["cluster_rank"]),
                "cluster_id": None if pd.isna(row["cluster_id"]) else str(row["cluster_id"]),
                "relevance_score": 0 if pd.isna(row["article_score"]) else float(row["article_score"]),
                "url_strong_tags": parse_json_cell(row["url_strong_tags"], []),
                "url_weak_tags": parse_json_cell(row["url_weak_tags"], []),
                "learned_scores": parse_json_cell(row["learned_scores_json"], {}),
                "learned_hits": parse_json_cell(row["learned_hits_json"], {}),
                "selector_reasons": None if pd.isna(row["reasons"]) else str(row["reasons"]),
                "record_kind": "article",
                "tag_status": "ranked",
                "tag_source": "url_thing_flash_selector",
            })

        for i in range(0, len(article_rows), 300):
            batch = article_rows[i:i + 300]
            upsert(base_url, service_key, "articles", batch, "run_id,url")
            total_pushed += len(batch)

        print(f"product={product} run_id={run_id} pushed={len(article_rows)}")

    print(f"date={args.date}")
    print(f"total_pushed={total_pushed}")


if __name__ == "__main__":
    main()
