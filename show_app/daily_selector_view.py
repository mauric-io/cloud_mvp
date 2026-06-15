#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from pathlib import Path
import json
import pandas as pd
import streamlit as st

ROOT = Path("/Users/mauricio/news_engine_tools")
CURRENT = ROOT / "cloud_mvp/data/daily_selector_current"

st.set_page_config(page_title="Daily Selector", layout="wide")

st.title("Daily Selector — ranked briefing candidates")

manifest_path = CURRENT / "manifest.json"
clusters_path = CURRENT / "daily_issue_clusters.csv"
articles_path = CURRENT / "daily_ranked_articles.csv"
packet_path = CURRENT / "daily_llm_candidate_packet.md"

if not manifest_path.exists():
    st.error("No daily selector set published yet.")
    st.code("python3 cloud_mvp/ingest/publish_daily_selector_to_streamlit.py --date $(date +%F)")
    st.stop()

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

st.caption(f"Date: {manifest.get('date')} | Source: {manifest.get('source_dir')}")

clusters = pd.read_csv(clusters_path) if clusters_path.exists() else pd.DataFrame()
articles = pd.read_csv(articles_path) if articles_path.exists() else pd.DataFrame()
packet = packet_path.read_text(encoding="utf-8") if packet_path.exists() else ""

c1, c2, c3 = st.columns(3)
c1.metric("Clusters", len(clusters))
c2.metric("Ranked articles", len(articles))
c3.metric("Packet chars", len(packet))

st.subheader("Top issue clusters")
if clusters.empty:
    st.warning("No clusters found.")
else:
    st.dataframe(clusters, use_container_width=True, hide_index=True)

st.subheader("Ranked articles")
if articles.empty:
    st.warning("No ranked articles found.")
else:
    cluster_ids = ["ALL"] + sorted(articles["cluster_id"].dropna().unique().tolist()) if "cluster_id" in articles.columns else ["ALL"]
    chosen = st.selectbox("Cluster", cluster_ids)
    view = articles if chosen == "ALL" else articles[articles["cluster_id"] == chosen]
    st.dataframe(view, use_container_width=True, hide_index=True)

st.subheader("LLM candidate packet")
st.download_button(
    "Download daily_llm_candidate_packet.md",
    data=packet,
    file_name=f"{manifest.get('date', 'daily')}_daily_llm_candidate_packet.md",
    mime="text/markdown",
)
st.text_area("Packet", packet, height=700)
