import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st
from supabase import create_client


APP_ROOT = Path(__file__).resolve().parent
TAXONOMY_PATH = APP_ROOT.parent / "config" / "taxonomy_v1.json"


st.set_page_config(
    page_title="Briefing Builder MVP",
    page_icon="🧭",
    layout="wide",
)


@st.cache_data
def load_taxonomy():
    with open(TAXONOMY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@st.cache_resource
def get_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")
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


def as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(x).strip() for x in value if str(x).strip()]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(x).strip() for x in parsed if str(x).strip()]
            if isinstance(parsed, dict):
                return []
        except Exception:
            return [value.strip()] if value.strip() else []
    return []


def as_dict(value):
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def merge_tag_values(row, keys):
    py_tags = as_dict(row.get("py_tags"))
    flash_tags = as_dict(row.get("flash_tags"))
    values = []
    for source in (py_tags, flash_tags):
        for key in keys:
            values.extend(as_list(source.get(key)))
    return sorted(set(v for v in values if v))


def fetch_articles(sb, product, date_from, date_to):
    if sb is None:
        local_path = APP_ROOT.parent / "data" / "local_articles.csv"
        if not local_path.exists():
            return pd.DataFrame()
        df = pd.read_csv(local_path)
        if "article_date" in df.columns:
            parsed_dates = pd.to_datetime(df["article_date"], format="mixed", errors="coerce")
            if parsed_dates.isna().any() and "run_date" in df.columns:
                fallback_dates = pd.to_datetime(df["run_date"], format="mixed", errors="coerce")
                parsed_dates = parsed_dates.fillna(fallback_dates)
            df["article_date"] = parsed_dates.dt.date
            df = df[df["article_date"].notna()]
            df = df[(df["article_date"] >= date_from) & (df["article_date"] <= date_to)]
        if "product" in df.columns:
            df = df[df["product"] == product]
        return df

    response = (
        sb.table("articles")
        .select("*")
        .eq("product", product)
        .gte("article_date", str(date_from))
        .lte("article_date", str(date_to))
        .limit(5000)
        .execute()
    )
    rows = response.data or []
    return pd.DataFrame(rows)


def row_matches(row, selected, keys):
    if not selected:
        return True
    values = set(merge_tag_values(row, keys))
    return bool(values.intersection(set(selected)))


def get_relevance(row):
    val = row.get("relevance_score")
    if val is None:
        flash_tags = as_dict(row.get("flash_tags"))
        val = flash_tags.get("briefing_relevance", 0)
    try:
        return float(val or 0)
    except Exception:
        return 0.0


def build_packet(df, product, date_from, date_to, selected_summary):
    lines = []
    lines.append(f"# Analyzer packet — {product}")
    lines.append("")
    lines.append(f"Date range: {date_from} to {date_to}")
    lines.append("")
    lines.append("## User selection")
    for key, value in selected_summary.items():
        lines.append(f"- {key}: {', '.join(value) if value else 'All'}")
    lines.append("")
    lines.append("## Candidate items")
    lines.append("")

    for i, row in df.head(80).iterrows():
        flash_tags = as_dict(row.get("flash_tags"))
        py_tags = as_dict(row.get("py_tags"))

        lines.append(f"### {row.get('title', '').strip()}")
        lines.append("")
        lines.append(f"- Date: {row.get('article_date', '')}")
        lines.append(f"- Outlet: {row.get('outlet', '')}")
        lines.append(f"- URL: {row.get('url', '')}")
        lines.append(f"- Relevance: {get_relevance(row)}")
        lines.append(f"- Temas: {', '.join(merge_tag_values(row, ['temas', 'themes', 'user_topics']))}")
        lines.append(f"- Empresas / sectores: {', '.join(merge_tag_values(row, ['empresas_sectores', 'companies_or_sectors', 'companies', 'sectors']))}")
        lines.append(f"- Entidades: {', '.join(merge_tag_values(row, ['entidades', 'entities']))}")
        lines.append(f"- Regiones: {', '.join(merge_tag_values(row, ['regiones', 'regions', 'geography']))}")
        why = flash_tags.get("why_relevant") or py_tags.get("why_relevant") or ""
        if why:
            lines.append(f"- Why relevant: {why}")
        lines.append("")

    return "\n".join(lines)


taxonomy = load_taxonomy()
sb = get_supabase()

st.title("Construye tu briefing")
st.caption("MVP cloud — controles simples para usuario; etiquetas internas quedan guardadas para ranking/análisis.")

if sb is None:
    st.info("Modo local: Supabase todavía no está configurado. La app leerá `cloud_mvp/data/local_articles.csv` si existe.")

col_a, col_b, col_c = st.columns([1, 1, 1])

with col_a:
    product = st.selectbox("Producto", ["nacional", "biz", "regiones"], index=0)

with col_b:
    default_to = date.today()
    default_from = default_to - timedelta(days=2)
    date_from = st.date_input("Desde", value=default_from)

with col_c:
    date_to = st.date_input("Hasta", value=default_to)

if date_from > date_to:
    st.error("La fecha inicial no puede ser posterior a la fecha final.")
    st.stop()

df = fetch_articles(sb, product, date_from, date_to)

if df.empty:
    st.warning("No hay artículos cargados para ese producto/rango. En modo local, falta crear `cloud_mvp/data/local_articles.csv` desde tus dos días reales.")
    st.stop()

for col in ["py_tags", "flash_tags"]:
    if col not in df.columns:
        df[col] = [{} for _ in range(len(df))]

df["relevance_num"] = df.apply(get_relevance, axis=1)

st.subheader("Filtros principales")

c1, c2 = st.columns(2)

with c1:
    selected_temas = st.multiselect("Temas", taxonomy["temas"])
    selected_empresas_sectores = st.multiselect("Empresas / sectores", taxonomy["empresas_sectores"])

with c2:
    selected_entidades = st.multiselect("Entidades", taxonomy["entidades"])
    selected_regiones = st.multiselect("Regiones", taxonomy["regiones"])

relevance_mode = st.radio(
    "Modo",
    ["Amplio", "Priorizar lo más relevante", "Solo señales fuertes"],
    horizontal=True,
    index=0,
)

show_advanced = bool(st.secrets.get("SHOW_ADVANCED_FILTERS", False))

selected_sources = []
selected_story_types = []
selected_risk_flags = []
selected_opportunity_flags = []

if show_advanced:
    with st.expander("Filtros avanzados / internos", expanded=False):
        available_sources = sorted(df["outlet"].dropna().astype(str).unique().tolist()) if "outlet" in df else []
        selected_sources = st.multiselect("Fuentes", available_sources)
        selected_story_types = st.multiselect("Tipo interno de hecho", taxonomy["internal_story_types"])
        selected_risk_flags = st.multiselect("Riesgos internos", taxonomy["internal_risk_flags"])
        selected_opportunity_flags = st.multiselect("Oportunidades internas", taxonomy["internal_opportunity_flags"])

filtered = df.copy()

filtered = filtered[
    filtered.apply(lambda r: row_matches(r, selected_temas, ["temas", "themes", "user_topics"]), axis=1)
]

filtered = filtered[
    filtered.apply(lambda r: row_matches(r, selected_empresas_sectores, ["empresas_sectores", "companies_or_sectors", "companies", "sectors"]), axis=1)
]

filtered = filtered[
    filtered.apply(lambda r: row_matches(r, selected_entidades, ["entidades", "entities"]), axis=1)
]

filtered = filtered[
    filtered.apply(lambda r: row_matches(r, selected_regiones, ["regiones", "regions", "geography"]), axis=1)
]

if selected_sources and "outlet" in filtered.columns:
    filtered = filtered[filtered["outlet"].isin(selected_sources)]

if selected_story_types:
    filtered = filtered[
        filtered.apply(lambda r: row_matches(r, selected_story_types, ["internal_story_type", "story_type"]), axis=1)
    ]

if selected_risk_flags:
    filtered = filtered[
        filtered.apply(lambda r: row_matches(r, selected_risk_flags, ["internal_risk_flags", "risk_flags"]), axis=1)
    ]

if selected_opportunity_flags:
    filtered = filtered[
        filtered.apply(lambda r: row_matches(r, selected_opportunity_flags, ["internal_opportunity_flags", "opportunity_flags"]), axis=1)
    ]

if relevance_mode == "Solo señales fuertes":
    filtered = filtered[filtered["relevance_num"] >= 4]

if relevance_mode in ["Priorizar lo más relevante", "Solo señales fuertes"]:
    filtered = filtered.sort_values("relevance_num", ascending=False)

st.divider()

m1, m2, m3 = st.columns(3)
m1.metric("Artículos cargados", len(df))
m2.metric("Artículos seleccionados", len(filtered))
m3.metric("Relevancia media", round(float(filtered["relevance_num"].mean()), 2) if not filtered.empty else 0)

preview_cols = [c for c in ["article_date", "outlet", "title", "relevance_num", "url"] if c in filtered.columns]

st.subheader("Vista previa")
st.dataframe(
    filtered[preview_cols].head(100),
    use_container_width=True,
    hide_index=True,
)

selected_summary = {
    "Temas": selected_temas,
    "Empresas / sectores": selected_empresas_sectores,
    "Entidades": selected_entidades,
    "Regiones": selected_regiones,
}

packet_text = build_packet(filtered, product, date_from, date_to, selected_summary)

st.subheader("Packet")
st.download_button(
    "Descargar analyzer packet .md",
    data=packet_text,
    file_name=f"{product}_{date_from}_{date_to}_analyzer_packet.md",
    mime="text/markdown",
)

with st.expander("Ver packet", expanded=False):
    st.text_area("Packet generado", packet_text, height=420)
