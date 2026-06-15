#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gzip
import json
from datetime import date, timedelta

import pandas as pd
import streamlit as st
from supabase import create_client


st.set_page_config(page_title="Daily Selector", layout="wide")

BUCKET_DEFAULT = "article-bodies"


@st.cache_resource
def get_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = (
        st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or st.secrets.get("SUPABASE_KEY", "")
    )

    bad_url = (
        not url
        or "YOUR_PROJECT" in url
        or "xxxxxxxx" in url
        or not url.startswith("https://")
        or not url.endswith(".supabase.co")
    )

    bad_key = (
        not key
        or "YOUR_SUPABASE" in key
        or "your-real-key" in key
    )

    if bad_url or bad_key:
        return None

    return create_client(url, key)


@st.cache_data(ttl=120)
def fetch_articles(product: str, date_from, date_to) -> pd.DataFrame:
    sb = get_supabase()

    if sb is None:
        return pd.DataFrame()

    response = (
        sb.table("articles")
        .select(
            "id,article_date,product,outlet,domain,title,url,"
            "cluster_rank,cluster_id,relevance_score,"
            "url_strong_tags,url_weak_tags,learned_scores,learned_hits,"
            "selector_reasons,body_storage_provider,body_storage_bucket,"
            "body_storage_key,body_char_count,body_sha256"
        )
        .eq("product", product)
        .gte("article_date", str(date_from))
        .lte("article_date", str(date_to))
        .order("article_date", desc=True)
        .order("cluster_rank", desc=False)
        .limit(5000)
        .execute()
    )

    rows = response.data or []
    df = pd.DataFrame(rows)

    if df.empty:
        return df

    if "relevance_score" in df.columns:
        df["relevance_score"] = pd.to_numeric(df["relevance_score"], errors="coerce").fillna(0)

    if "cluster_rank" in df.columns:
        df["cluster_rank"] = pd.to_numeric(df["cluster_rank"], errors="coerce")

    return df


@st.cache_data(ttl=600)
def fetch_body(bucket: str, storage_key: str) -> dict:
    sb = get_supabase()

    if sb is None:
        raise RuntimeError("Supabase is not configured.")

    if not bucket:
        bucket = BUCKET_DEFAULT

    raw = sb.storage.from_(bucket).download(storage_key)

    if isinstance(raw, str):
        raw = raw.encode("utf-8")

    try:
        decoded = gzip.decompress(raw)
    except Exception:
        decoded = raw

    return json.loads(decoded.decode("utf-8"))


def fmt_tags(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(x) for x in value)
    if isinstance(value, dict):
        return ", ".join(str(k) for k in value.keys())
    return str(value)


def body_status(row) -> str:
    key = row.get("body_storage_key")
    chars = row.get("body_char_count")
    if not key:
        return "No body"
    try:
        chars = int(chars)
    except Exception:
        chars = 0
    return f"Body OK ({chars:,} chars)"


st.title("Daily Selector — Supabase")

sb = get_supabase()

if sb is None:
    st.error("Supabase secrets are not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY/SUPABASE_KEY.")
    st.stop()

c1, c2, c3 = st.columns(3)

with c1:
    product = st.selectbox("Producto", ["nacional", "biz", "regiones"], index=0)

with c2:
    default_to = date.today()
    default_from = default_to - timedelta(days=2)
    date_from = st.date_input("Desde", value=default_from)

with c3:
    date_to = st.date_input("Hasta", value=default_to)

if date_from > date_to:
    st.error("La fecha inicial no puede ser posterior a la fecha final.")
    st.stop()

articles = fetch_articles(product, date_from, date_to)

if articles.empty:
    st.warning("No hay artículos en Supabase para ese producto/rango.")
    st.stop()

articles["body_status"] = articles.apply(body_status, axis=1)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Articles", len(articles))
m2.metric("Unique URLs", articles["url"].nunique() if "url" in articles.columns else 0)
m3.metric("Clusters", articles["cluster_id"].nunique() if "cluster_id" in articles.columns else 0)
m4.metric("With body", int(articles["body_storage_key"].notna().sum()) if "body_storage_key" in articles.columns else 0)

st.subheader("Filtros")

cluster_ids = ["ALL"] + sorted(
    [str(x) for x in articles["cluster_id"].dropna().unique().tolist()]
) if "cluster_id" in articles.columns else ["ALL"]

outlets = ["ALL"] + sorted(
    [str(x) for x in articles["outlet"].dropna().unique().tolist()]
) if "outlet" in articles.columns else ["ALL"]

f1, f2, f3 = st.columns(3)

with f1:
    chosen_cluster = st.selectbox("Cluster", cluster_ids)

with f2:
    chosen_outlet = st.selectbox("Outlet", outlets)

with f3:
    min_score = st.slider(
        "Min score",
        min_value=0.0,
        max_value=15.0,
        value=0.0,
        step=0.25,
    )

view = articles.copy()

if chosen_cluster != "ALL":
    view = view[view["cluster_id"].astype(str) == chosen_cluster]

if chosen_outlet != "ALL":
    view = view[view["outlet"].astype(str) == chosen_outlet]

if "relevance_score" in view.columns:
    view = view[view["relevance_score"] >= min_score]

sort_cols = [c for c in ["article_date", "cluster_rank", "relevance_score"] if c in view.columns]
if sort_cols:
    ascending = [False if c == "article_date" else True for c in sort_cols]
    view = view.sort_values(sort_cols, ascending=ascending)

st.subheader("Ranked articles")

display_cols = [
    "article_date",
    "product",
    "cluster_rank",
    "cluster_id",
    "relevance_score",
    "outlet",
    "domain",
    "title",
    "url",
    "url_strong_tags",
    "selector_reasons",
    "body_status",
]

display_cols = [c for c in display_cols if c in view.columns]

st.dataframe(
    view[display_cols],
    use_container_width=True,
    hide_index=True,
)

st.subheader("Article bodies")

max_items = st.slider("Body preview count", 5, 50, 15, 5)

for _, row in view.head(max_items).iterrows():
    title = str(row.get("title", "")).strip()
    outlet = str(row.get("outlet", "") or "")
    score = row.get("relevance_score", "")
    storage_key = row.get("body_storage_key")
    bucket = row.get("body_storage_bucket") or BUCKET_DEFAULT

    label = f"{row.get('article_date', '')} | {outlet} | score {score} | {title[:120]}"

    with st.expander(label, expanded=False):
        st.write(f"**URL:** {row.get('url', '')}")
        st.write(f"**Cluster:** {row.get('cluster_id', '')} / rank {row.get('cluster_rank', '')}")
        st.write(f"**Strong URL tags:** {fmt_tags(row.get('url_strong_tags'))}")
        st.write(f"**Reasons:** {row.get('selector_reasons', '')}")

        if not storage_key:
            st.warning("No body_storage_key for this article.")
            continue

        try:
            payload = fetch_body(bucket, storage_key)
        except Exception as e:
            st.error(f"Could not fetch body from Storage: {e}")
            continue

        body = payload.get("body", "")
        st.caption(f"Storage: {bucket}/{storage_key}")
        st.caption(f"Chars: {len(body):,} | SHA256: {payload.get('body_sha256', '')[:16]}")
        st.text_area("Body", body, height=350, key=f"body_{row.get('id')}")
