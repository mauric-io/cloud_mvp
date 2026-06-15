#!/usr/bin/env python3
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import requests


ROOT = Path("/Users/mauricio/news_engine_tools")
BUCKET = "article-bodies"
PROVIDER = "supabase_storage"

BODY_NAME_RE = re.compile(
    r"(body|text|content|full|article_text|clean_text|raw_text|nota|paragraph|html)",
    re.I,
)
BAD_BODY_NAMES = {
    "url", "article_url", "canonical_url", "source_url", "link", "href",
    "title", "headline", "article_title", "outlet", "source", "domain",
    "date", "published_at", "published_date",
}
URL_CANDIDATES = ["url", "article_url", "canonical_url", "source_url", "link", "href"]


def env_required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing env var: {name}")
    return value


def api_headers(key: str) -> dict:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def json_headers(key: str) -> dict:
    return {
        **api_headers(key),
        "Content-Type": "application/json",
    }


def upload_headers(key: str) -> dict:
    return {
        **api_headers(key),
        "Content-Type": "application/json",
        "Cache-Control": "3600",
        "x-upsert": "true",
    }


def find_url_cols(cols):
    out = []
    for c in cols:
        cl = c.lower().strip()
        if cl in URL_CANDIDATES or cl.endswith("_url"):
            out.append(c)
    return out


def find_body_cols(cols):
    out = []
    for c in cols:
        cl = c.lower().strip()
        if cl in BAD_BODY_NAMES:
            continue
        if BODY_NAME_RE.search(c):
            out.append(c)
    return out


def candidate_csvs(date: str):
    run_root = ROOT / "scrape_outlets" / "data" / "runs" / date
    out = []
    for p in run_root.rglob("*.csv"):
        name = p.name.lower()
        parent = str(p.parent).lower()
        if (
            "raw" in parent
            or "merged" in parent
            or "analysis" in parent
            or "df_auth" in parent
            or "df_only" in parent
            or "non_mercurio/fast" in parent
        ):
            if any(x in name for x in [
                "articles",
                "raw_articles",
                "merged",
                "df_clean",
                "analyzed_all",
                "unique_regiones",
                "briefing_relevant",
                "regiones_relevant",
                "biz_relevant",
            ]):
                out.append(p)
    return sorted(set(out))


def slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace("www.", "") or "unknown-domain"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"{host}/{digest}.json.gz"


def get_supabase_articles(base_url: str, key: str, date: str):
    rows = []
    offset = 0
    limit = 1000

    while True:
        r = requests.get(
            f"{base_url}/rest/v1/articles",
            headers=api_headers(key),
            params={
                "select": "id,article_date,product,url,title",
                "article_date": f"eq.{date}",
                "limit": str(limit),
                "offset": str(offset),
                "order": "product.asc",
            },
            timeout=60,
        )

        if r.status_code != 200:
            raise SystemExit(f"Supabase read failed: {r.status_code} {r.text}")

        batch = r.json()
        rows.extend(batch)

        if len(batch) < limit:
            break

        offset += limit

    return rows


def build_body_lookup(date: str, selector_urls: set[str]):
    candidates = []

    for p in candidate_csvs(date):
        try:
            cols = pd.read_csv(p, nrows=0).columns.tolist()
        except Exception:
            continue

        url_cols = find_url_cols(cols)
        body_cols = find_body_cols(cols)

        if not url_cols or not body_cols:
            continue

        usecols = list(dict.fromkeys(url_cols + body_cols))

        try:
            df = pd.read_csv(p, dtype=str, usecols=usecols, on_bad_lines="skip")
        except Exception:
            continue

        for url_col in url_cols:
            if url_col not in df.columns:
                continue

            urls = df[url_col].fillna("").astype(str).str.strip()
            overlap = set(urls[urls != ""]) & selector_urls

            if not overlap:
                continue

            sub = df[urls.isin(overlap)].copy()

            for body_col in body_cols:
                if body_col not in sub.columns:
                    continue

                s = sub[body_col].fillna("").astype(str)
                gt200 = int((s.str.len() > 200).sum())
                gt500 = int((s.str.len() > 500).sum())
                maxlen = int(s.str.len().max()) if len(s) else 0

                if gt200 == 0:
                    continue

                candidates.append({
                    "path": p,
                    "url_col": url_col,
                    "body_col": body_col,
                    "matched_urls": len(overlap),
                    "gt500": gt500,
                    "gt200": gt200,
                    "maxlen": maxlen,
                })

    candidates = sorted(
        candidates,
        key=lambda x: (x["matched_urls"], x["gt500"], x["gt200"], x["maxlen"]),
        reverse=True,
    )

    body_by_url = {}
    source_by_url = {}

    for c in candidates:
        need = selector_urls - set(body_by_url)
        if not need:
            break

        try:
            df = pd.read_csv(
                c["path"],
                dtype=str,
                usecols=[c["url_col"], c["body_col"]],
                on_bad_lines="skip",
            )
        except Exception:
            continue

        for _, row in df.iterrows():
            url = "" if pd.isna(row[c["url_col"]]) else str(row[c["url_col"]]).strip()
            if url not in need or url in body_by_url:
                continue

            body = "" if pd.isna(row[c["body_col"]]) else str(row[c["body_col"]])
            if len(body) <= 200:
                continue

            body_by_url[url] = body
            source_by_url[url] = {
                "source_csv": str(c["path"]),
                "body_col": c["body_col"],
            }

    return body_by_url, source_by_url


def upload_object(base_url: str, key: str, storage_key: str, payload: dict):
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    compressed = gzip.compress(raw)

    r = requests.post(
        f"{base_url}/storage/v1/object/{BUCKET}/{storage_key}",
        headers={
            **api_headers(key),
            "Content-Type": "application/gzip",
            "Cache-Control": "3600",
            "x-upsert": "true",
        },
        data=compressed,
        timeout=90,
    )

    if r.status_code not in (200, 201):
        print(r.text, file=sys.stderr)
        raise SystemExit(f"Storage upload failed: {r.status_code} key={storage_key}")

    return len(compressed)


def patch_article_rows(base_url: str, key: str, article_ids: list[str], patch: dict):
    for article_id in article_ids:
        r = requests.patch(
            f"{base_url}/rest/v1/articles",
            headers={
                **json_headers(key),
                "Prefer": "return=minimal",
            },
            params={"id": f"eq.{article_id}"},
            data=json.dumps(patch, ensure_ascii=False),
            timeout=60,
        )

        if r.status_code not in (200, 204):
            print(r.text, file=sys.stderr)
            raise SystemExit(f"Article patch failed: {r.status_code} id={article_id}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    base_url = env_required("SUPABASE_URL").rstrip("/")
    key = env_required("SUPABASE_SERVICE_ROLE_KEY")

    articles = get_supabase_articles(base_url, key, args.date)
    selector_urls = set(a["url"].strip() for a in articles if a.get("url"))

    body_by_url, source_by_url = build_body_lookup(args.date, selector_urls)
    missing = selector_urls - set(body_by_url)

    by_url_article_ids = {}
    for a in articles:
        u = a.get("url", "").strip()
        if not u:
            continue
        by_url_article_ids.setdefault(u, []).append(a["id"])

    print(f"date={args.date}")
    print(f"supabase_article_rows={len(articles)}")
    print(f"unique_urls={len(selector_urls)}")
    print(f"body_matches={len(body_by_url)}")
    print(f"missing_bodies={len(missing)}")

    if missing:
        print("missing sample:")
        for u in sorted(missing)[:10]:
            print(" -", u)
        raise SystemExit("Refusing upload because some selector URLs have no body match.")

    total_uncompressed = 0
    total_compressed = 0
    objects_uploaded = 0
    article_rows_patched = 0

    for url in sorted(body_by_url):
        body = body_by_url[url]
        source = source_by_url[url]

        body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        head_sha = hashlib.sha256(body[:1000].encode("utf-8")).hexdigest()
        storage_key = f"articles/{args.date}/{slug_from_url(url)}"

        payload = {
            "article_date": args.date,
            "url": url,
            "body": body,
            "body_sha256": body_sha,
            "body_head_sha256": head_sha,
            "body_char_count": len(body),
            "source_csv": source["source_csv"],
            "source_col": source["body_col"],
        }

        article_ids = by_url_article_ids.get(url, [])

        patch = {
            "body_storage_provider": PROVIDER,
            "body_storage_bucket": BUCKET,
            "body_storage_key": storage_key,
            "body_r2_key": None,
            "body_sha256": body_sha,
            "body_head_sha256": head_sha,
            "body_char_count": len(body),
            "body_source_csv": source["source_csv"],
            "body_source_col": source["body_col"],
            "body_uploaded_at": datetime.now(timezone.utc).isoformat(),
        }

        total_uncompressed += len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

        if args.dry_run:
            if objects_uploaded < 5:
                print(json.dumps({
                    "url": url,
                    "storage_key": storage_key,
                    "article_rows_to_patch": len(article_ids),
                    "body_char_count": len(body),
                    "source_csv": source["source_csv"],
                    "body_sha256_prefix": body_sha[:16],
                }, ensure_ascii=False, indent=2))
            objects_uploaded += 1
            article_rows_patched += len(article_ids)
            continue

        compressed_size = upload_object(base_url, key, storage_key, payload)
        patch_article_rows(base_url, key, article_ids, patch)

        objects_uploaded += 1
        article_rows_patched += len(article_ids)
        total_compressed += compressed_size

    print(f"planned_or_uploaded_objects={objects_uploaded}")
    print(f"planned_or_patched_article_rows={article_rows_patched}")
    print(f"approx_uncompressed_json_bytes={total_uncompressed}")

    if not args.dry_run:
        print(f"compressed_uploaded_bytes={total_compressed}")


if __name__ == "__main__":
    main()
