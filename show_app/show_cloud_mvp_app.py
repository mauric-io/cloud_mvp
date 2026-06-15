from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st


APP_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = APP_ROOT / "data"
DATES_ROOT = DATA_ROOT / "daily_selector_dates"


st.set_page_config(
    page_title="Selector briefing cloud MVP",
    layout="wide",
)


def load_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        st.error(f"Falta archivo: {path.relative_to(APP_ROOT)}")
        st.stop()
    return pd.read_csv(path)


def available_dates() -> list[str]:
    if not DATES_ROOT.exists():
        st.error(f"No existe: {DATES_ROOT.relative_to(APP_ROOT)}")
        st.stop()

    dates = []
    for p in DATES_ROOT.iterdir():
        if p.is_dir() and (p / "daily_ranked_articles.csv").exists():
            dates.append(p.name)

    dates = sorted(dates)
    if not dates:
        st.error("No hay fechas selector cargadas en data/daily_selector_dates/")
        st.stop()
    return dates


def run_dir(run_date: str) -> Path:
    return DATES_ROOT / run_date


def load_manifest(run_date: str) -> dict:
    p = run_dir(run_date) / "manifest.json"
    if not p.exists():
        return {"run_date": run_date, "manifest_status": "missing"}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return {"run_date": run_date, "manifest_status": f"bad json: {e}"}


def payload_summary(run_date: str) -> dict:
    rdir = run_dir(run_date)
    ranked = load_csv(rdir / "daily_ranked_articles.csv")
    clusters = load_csv(rdir / "daily_issue_clusters.csv")

    out = {
        "date": run_date,
        "total_rows": len(ranked),
        "unique_urls": ranked["url"].nunique() if "url" in ranked.columns else None,
        "clusters": len(clusters),
        "nacional": 0,
        "biz": 0,
        "regiones": 0,
        "manifest": "ok" if (rdir / "manifest.json").exists() else "missing",
    }

    if "product" in ranked.columns:
        vc = ranked["product"].fillna("UNKNOWN").astype(str).str.lower().value_counts()
        out["nacional"] = int(vc.get("nacional", 0))
        out["biz"] = int(vc.get("biz", 0))
        out["regiones"] = int(vc.get("regiones", 0))

    return out


def validate_payload(run_date: str) -> None:
    rdir = run_dir(run_date)
    required = [
        "daily_ranked_articles.csv",
        "daily_issue_clusters.csv",
        "manifest.json",
    ]

    missing = [f for f in required if not (rdir / f).exists()]
    if missing:
        st.error(f"Payload incompleto para {run_date}. Faltan: {', '.join(missing)}")
        st.stop()

    ranked = load_csv(rdir / "daily_ranked_articles.csv")
    if "url" not in ranked.columns:
        st.error(f"Payload inválido para {run_date}: falta columna url")
        st.stop()

    if ranked["url"].dropna().astype(str).nunique() == 0:
        st.error(f"Payload inválido para {run_date}: URL set vacío")
        st.stop()

    manifest = load_manifest(run_date)
    manifest_date = (
        manifest.get("run_date")
        or manifest.get("date")
        or manifest.get("payload_date")
    )
    if manifest_date and str(manifest_date) != run_date:
        st.error(
            f"Manifest inválido: carpeta {run_date}, manifest dice {manifest_date}"
        )
        st.stop()


st.title("Selector briefing cloud MVP")
st.caption("Lee payloads fechados desde data/daily_selector_dates/. No usa local_articles.csv.")

dates = available_dates()
summary_df = pd.DataFrame([payload_summary(d) for d in dates])

st.subheader("Payloads disponibles")
st.dataframe(summary_df, use_container_width=True, hide_index=True)

default_idx = len(dates) - 1
selected_date = st.selectbox("Fecha", dates, index=default_idx)

validate_payload(selected_date)

rdir = run_dir(selected_date)
ranked = load_csv(rdir / "daily_ranked_articles.csv")
clusters = load_csv(rdir / "daily_issue_clusters.csv")
manifest = load_manifest(selected_date)

st.subheader(f"Detalle selector — {selected_date}")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Artículos", len(ranked))
c2.metric("URLs únicas", ranked["url"].nunique() if "url" in ranked.columns else 0)
c3.metric("Clusters", len(clusters))
c4.metric("Manifest", "ok" if (rdir / "manifest.json").exists() else "missing")

if "product" in ranked.columns:
    products = ["todos"] + sorted(ranked["product"].dropna().astype(str).unique().tolist())
    product = st.selectbox("Producto", products)
    if product != "todos":
        ranked_view = ranked[ranked["product"].astype(str) == product].copy()
    else:
        ranked_view = ranked.copy()
else:
    ranked_view = ranked.copy()

st.write(f"Mostrando {len(ranked_view)} artículos")

preferred_cols = [
    "product",
    "rank",
    "rank_score",
    "outlet",
    "source",
    "title",
    "url",
    "cluster_id",
    "issue",
    "category",
    "date",
]

cols = [c for c in preferred_cols if c in ranked_view.columns]
if not cols:
    cols = ranked_view.columns.tolist()

st.dataframe(ranked_view[cols], use_container_width=True, hide_index=True)

with st.expander("Clusters"):
    st.dataframe(clusters, use_container_width=True, hide_index=True)

with st.expander("Manifest"):
    st.json(manifest)

packet = rdir / "daily_llm_candidate_packet.md"
report = rdir / "daily_selector_report.md"

d1, d2 = st.columns(2)
if packet.exists():
    d1.download_button(
        "Descargar packet LLM",
        packet.read_text(encoding="utf-8"),
        file_name=f"{selected_date}_daily_llm_candidate_packet.md",
    )
if report.exists():
    d2.download_button(
        "Descargar reporte selector",
        report.read_text(encoding="utf-8"),
        file_name=f"{selected_date}_daily_selector_report.md",
    )
