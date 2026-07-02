from __future__ import annotations

import json
import os
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
import streamlit as st

from v6_briefing_supabase import repair_length
import JasonMaker

# --- BEGIN V6 HARD FACET SCRUBBER ---
def _v6_install_hard_facet_scrubber():
    import re
    import unicodedata
    import streamlit as st

    if getattr(st, "_v6_hard_facet_scrubber_installed", False):
        return

    original_multiselect = st.multiselect

    TOPICS = [
        "Política", "Economía", "Empresas", "Minería", "Energía", "Seguridad",
        "Judicial", "Salud", "Educación", "Regiones", "Internacional",
        "Logística / Comercio exterior", "Medioambiente", "Tecnología / IA",
        "Opinión", "Salmonicultura / Acuicultura",
    ]

    TOPIC_RX = {
        "Política": r"polit|gobierno|congreso|senado|diputad|eleccion|la moneda|ministerio|ministro|reforma",
        "Economía": r"econom|hacienda|banco central|imacec|ipc|inflacion|pib|mercado|empleo|tribut",
        "Empresas": r"empresa|compañ|negocio|industria|retail|holding|directorio|gerente|startup",
        "Minería": r"mineri|cobre|litio|codelco|enami|sqm|collahuasi|escondida|sonami",
        "Energía": r"energ|electric|solar|eolic|hidrogen|gas|combustible|enap|comision nacional de energia|cne",
        "Seguridad": r"seguridad|delito|homicidio|carabinero|pdi|fiscalia|narcotrafico|violencia",
        "Judicial": r"judicial|tribunal|corte|suprema|juez|querella|fallo|formaliz",
        "Salud": r"salud|hospital|clinica|isapre|fonasa|medic|licencia medica",
        "Educación": r"educacion|colegio|liceo|universidad|estudiante|mineduc|paes",
        "Regiones": r"region|regional|municip|gobernador|valparaiso|biobio|antofagasta|araucania|lagos|rios",
        "Internacional": r"internacional|eeuu|china|argentina|brasil|peru|bolivia|gaza|israel|rusia|ucrania",
        "Logística / Comercio exterior": r"logistica|comercio exterior|puerto|aduana|maritimo|transporte|carga",
        "Medioambiente": r"medioambiente|ambiental|agua|sequia|contaminacion|sma|sea|evaluacion ambiental",
        "Tecnología / IA": r"tecnologia|inteligencia artificial|\bia\b|software|ciberseguridad|datos",
        "Opinión": r"opinion|columna",
        "Salmonicultura / Acuicultura": r"salmon|acuicultura",
    }

    ACTION_RX = re.compile(
        r"^\s*(compartir|comunicado|comunicado de prensa|ver más|ver mas|leer más|leer mas|"
        r"actualidad|contenido patrocinado|suscr[ií]bete|newsletter|lo último|lo ultimo)\b",
        re.I,
    )

    ORG_RX = re.compile(
        r"\b(comisi[oó]n|ministerio|subsecretar[ií]a|superintendencia|servicio|direcci[oó]n|"
        r"fiscal[ií]a|contralor[ií]a|corte|tribunal|senado|c[aá]mara|banco|empresa|grupo|"
        r"holding|fundaci[oó]n|corporaci[oó]n|asociaci[oó]n|codelco|enami|sqm|enel|copec|"
        r"abastible|hub|metro|pdi|carabineros|cne|sea|sma)\b",
        re.I,
    )

    REGION_RX = re.compile(
        r"\b(arica|parinacota|tarapac[aá]|antofagasta|atacama|coquimbo|valpara[ií]so|"
        r"metropolitana|santiago|ohiggins|maule|ñuble|nuble|biob[ií]o|araucan[ií]a|"
        r"los r[ií]os|los lagos|ays[eé]n|magallanes)\b",
        re.I,
    )

    PERSON_LIKE_RX = re.compile(
        r"^[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|las|los|y|al)?\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,5}$"
    )

    BAD_RX = re.compile(r"\b(select all|shtml|html|www|newsletter|hor[oó]scopo|zodiaco)\b", re.I)

    def raw(x):
        return re.sub(r"\s*\(\d+\)\s*$", "", str(x or "").strip())

    def norm(x):
        s = raw(x)
        s = unicodedata.normalize("NFKD", s)
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return re.sub(r"\s+", " ", s).lower().strip()

    def bad(x):
        s = raw(x)
        low = norm(s)
        return (
            not low
            or len(low) < 2
            or ACTION_RX.search(s)
            or BAD_RX.search(s)
            or low in {"que", "del", "por", "para", "con", "sin", "una", "uno", "los", "las", "este", "esta"}
        )

    def canonical_topics(raw_options):
        blob = " | ".join(norm(o) for o in (raw_options or []) if not bad(o))
        return [t for t in TOPICS if re.search(TOPIC_RX[t], blob, re.I)]

    def raw_terms_for_topics(raw_options, selected_topics):
        out = []
        seen = set()

        for opt in raw_options or []:
            if bad(opt):
                continue

            low = norm(opt)

            for topic in selected_topics or []:
                if topic not in TOPIC_RX:
                    continue

                if re.search(TOPIC_RX[topic], low, re.I):
                    key = str(opt)
                    if key not in seen:
                        seen.add(key)
                        out.append(opt)

        return out

    def keep_org(x):
        s = raw(x)
        if bad(s):
            return False
        if len(norm(s).split()) > 7:
            return False
        if PERSON_LIKE_RX.match(s) and not ORG_RX.search(s):
            return False
        return bool(ORG_RX.search(s))

    def keep_region(x):
        s = raw(x)
        return bool(not bad(s) and REGION_RX.search(s))

    def clean_default(default, allowed):
        allowed = set(allowed)
        if default is None:
            return default
        if isinstance(default, str):
            return default if default in allowed else None
        try:
            return [x for x in default if x in allowed]
        except Exception:
            return default

    def scrub(label, options):
        opts = list(options or [])
        label_low = norm(label)

        if "empresa" in label_low or "compañ" in label_low or "company" in label_low:
            return [o for o in opts if keep_org(o)]

        if "entidad" in label_low or "actor" in label_low:
            return [o for o in opts if keep_org(o)]

        if "region" in label_low:
            return [o for o in opts if keep_region(o)]

        return opts

    def patched_multiselect(label, options=None, *args, **kwargs):
        raw_options = list(options or [])
        label_low = norm(label)

        if "tema" in label_low:
            canonical = canonical_topics(raw_options)

            if "default" in kwargs:
                kwargs["default"] = clean_default(kwargs["default"], canonical)

            if args:
                args = list(args)
                args[0] = clean_default(args[0], canonical)
                args = tuple(args)

            selected_canonical = original_multiselect(label, canonical, *args, **kwargs)

            # Critical fix:
            # UI shows canonical topics, but original downstream filter receives raw matching tokens.
            return raw_terms_for_topics(raw_options, selected_canonical)

        cleaned = scrub(label, raw_options)

        if cleaned != raw_options:
            options = cleaned
            if "default" in kwargs:
                kwargs["default"] = clean_default(kwargs["default"], cleaned)
            if args:
                args = list(args)
                args[0] = clean_default(args[0], cleaned)
                args = tuple(args)

        return original_multiselect(label, options, *args, **kwargs)

    st.multiselect = patched_multiselect
    st._v6_hard_facet_scrubber_installed = True


_v6_install_hard_facet_scrubber()
# --- END V6 HARD FACET SCRUBBER ---




MODE_SPECS = {
    "one_pager": {"label": "1-pager", "min_chars": 3000, "max_chars": 5000, "target_chars": 4500},
    "exec": {"label": "Resumen ejecutivo", "min_chars": 5000, "max_chars": 10000, "target_chars": 8500},
    "dossier": {"label": "Dossier", "min_chars": 15000, "max_chars": 25000, "target_chars": 22000},
}

VIEW_NAME = "v_articles_with_v6_search_tags"

PRODUCTS = ["Todos", "nacional", "biz", "regiones"]

TEMA_COLS = [
    "primary_labels_json",
    "secondary_labels_json",
    "weak_labels_json",
    "search_terms_json",
    "primary_theme",
    "primary_theme_display",
    "secondary_themes",
    "topics",
]

EMPRESA_SECTOR_COLS = [
    "organization_entities_json",
    "primary_labels_json",
    "secondary_labels_json",
    "search_terms_json",
    "companies",
    "sectors",
    "empresas_sectores",
]

ENTIDAD_COLS = [
    "search_entities_json",
    "people_entities_json",
    "organization_entities_json",
    "unknown_entities_json",
    "entities",
]

REGION_COLS = [
    "place_entities_json",
    "regions",
    "regiones",
    "geography",
    "zone",
]

SEARCH_COLS = [
    "free_search_text",
    "title",
    "outlet",
    "domain",
    "description",
    "selector_reasons",
    "url",
    "article_date",
    "product",
    "primary_labels_json",
    "secondary_labels_json",
    "weak_labels_json",
    "search_terms_json",
    "search_entities_json",
    "people_entities_json",
    "organization_entities_json",
    "place_entities_json",
    "unknown_entities_json",
    "primary_theme",
    "secondary_themes",
    "entities",
    "topics",
    "signals",
    "match_terms",
]


def _read_secrets_flat() -> dict[str, Any]:
    try:
        import tomllib
    except Exception:
        return {}

    out: dict[str, Any] = {}
    for p in [
        Path(".streamlit/secrets.toml"),
        Path("show_app/.streamlit/secrets.toml"),
        Path("secrets.toml"),
    ]:
        if not p.exists():
            continue
        try:
            data = tomllib.loads(p.read_text())
        except Exception:
            continue
        for k, v in data.items():
            if isinstance(v, dict):
                for kk, vv in v.items():
                    out[str(kk)] = vv
                    out[f"{k}.{kk}"] = vv
            else:
                out[str(k)] = v
    return out


def _secret(flat: dict[str, Any], names: list[str]) -> str:
    for name in names:
        if os.environ.get(name):
            return os.environ[name].strip()
        if name in flat and flat[name]:
            return str(flat[name]).strip()
    return ""


def _supabase_config() -> tuple[str, str]:
    flat = _read_secrets_flat()
    url = _secret(flat, ["SUPABASE_URL", "supabase.SUPABASE_URL"]).rstrip("/")
    key = _secret(
        flat,
        [
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_ANON_KEY",
            "SUPABASE_KEY",
            "supabase.SUPABASE_SERVICE_ROLE_KEY",
            "supabase.SUPABASE_ANON_KEY",
            "supabase.SUPABASE_KEY",
        ],
    )
    if not url or not key:
        st.error("Missing SUPABASE_URL and Supabase key in secrets/env.")
        st.stop()
    return url, key


def _headers(key: str) -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": "count=exact",
    }


def _norm(value: Any) -> str:
    value = "" if value is None else str(value)
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r"[^a-z0-9%$]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _jsonish_values(value: Any) -> list[str]:
    if value is None:
        return []
    try:
        if pd.isna(value):
            return []
    except Exception:
        pass

    if isinstance(value, list):
        raw = value
    elif isinstance(value, dict):
        raw = [value]
    else:
        txt = str(value).strip()
        if not txt or txt.lower() == "nan":
            return []
        try:
            raw = json.loads(txt)
        except Exception:
            raw = re.split(r"[,;|]", txt)

    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        raw = [raw]

    out: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            val = (
                item.get("name")
                or item.get("label")
                or item.get("text")
                or item.get("value")
                or item.get("entity")
                or item.get("term")
            )
            if val:
                out.append(str(val).strip())
        else:
            val = str(item).strip()
            if val:
                out.append(val)

    seen: set[str] = set()
    clean: list[str] = []
    for val in out:
        key = _norm(val)
        if key and key not in seen:
            clean.append(val)
            seen.add(key)
    return clean


def _row_values(row: pd.Series, cols: list[str]) -> list[str]:
    vals: list[str] = []
    for col in cols:
        if col in row.index:
            vals.extend(_jsonish_values(row.get(col)))
    return vals


def _options(df: pd.DataFrame, cols: list[str], limit: int = 500) -> list[str]:
    vals: list[str] = []
    for _, row in df.iterrows():
        vals.extend(_row_values(row, cols))
    return sorted({v for v in vals if v}, key=_norm)[:limit]


def _matches_selected(row: pd.Series, selected: list[str], cols: list[str]) -> bool:
    if not selected:
        return True
    row_vals = {_norm(v) for v in _row_values(row, cols)}
    selected_vals = {_norm(v) for v in selected}
    return bool(row_vals.intersection(selected_vals))


def _search_blob(row: pd.Series) -> str:
    parts: list[str] = []
    for col in SEARCH_COLS:
        if col in row.index:
            val = row.get(col)
            parts.append(str(val or ""))
            parts.extend(_jsonish_values(val))
    return _norm(" ".join(parts))


def _matches_search(row: pd.Series, query: str) -> bool:
    q = _norm(query)
    if not q:
        return True
    blob = _search_blob(row)
    return all(tok in blob for tok in q.split())


def _score(row: pd.Series) -> float:
    for col in [
        "relative_relevance_pct",
        "relevance_score_used_value",
        "relevance_score",
        "score",
        "cluster_rank",
    ]:
        if col not in row.index:
            continue
        try:
            val = row.get(col)
            if val is not None and str(val).strip() != "":
                return float(val)
        except Exception:
            pass
    return 0.0


def _join(row: pd.Series, cols: list[str], n: int = 5) -> str:
    return ", ".join(_row_values(row, cols)[:n])


def _safe_article_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_v6_corpus(base_url: str, key: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    page = 1000
    start = 0

    while True:
        r = requests.get(
            f"{base_url}/rest/v1/{VIEW_NAME}",
            headers={
                **_headers(key),
                "Range-Unit": "items",
                "Range": f"{start}-{start + page - 1}",
            },
            params={
                "select": "*",
                "order": "article_date.desc,product.asc,outlet.asc",
            },
            timeout=90,
        )
        if r.status_code not in (200, 206):
            raise RuntimeError(f"Supabase fetch failed {r.status_code}: {r.text[:1200]}")
        batch = r.json()
        if not isinstance(batch, list):
            raise RuntimeError(f"Supabase returned non-list payload: {str(batch)[:500]}")
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page

    return pd.DataFrame(rows)


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in [
        "article_date",
        "product",
        "outlet",
        "title",
        "url",
        "domain",
        "description",
        "selector_reasons",
        "free_search_text",
    ]:
        if col not in df.columns:
            df[col] = ""
    df["article_date"] = _safe_article_date(df["article_date"])
    df = df[df["article_date"].notna()].copy()
    df["_score"] = df.apply(_score, axis=1)
    df["_temas_ui"] = df.apply(lambda r: _join(r, TEMA_COLS, 4), axis=1)
    df["_entidades_ui"] = df.apply(lambda r: _join(r, ENTIDAD_COLS, 4), axis=1)
    df["_regiones_ui"] = df.apply(lambda r: _join(r, REGION_COLS, 3), axis=1)
    return df


def _packet_source(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    def tags(row: pd.Series) -> list[str]:
        vals: list[str] = []
        for cols in [TEMA_COLS, EMPRESA_SECTOR_COLS, ENTIDAD_COLS, REGION_COLS]:
            vals.extend(_row_values(row, cols))
        seen: set[str] = set()
        clean: list[str] = []
        for val in vals:
            key = _norm(val)
            if key and key not in seen:
                clean.append(val)
                seen.add(key)
        return clean[:30]

    out["v6_tags"] = out.apply(tags, axis=1)
    out["tags"] = out["v6_tags"]
    out["selector_reasons"] = out.apply(
        lambda r: " | ".join(
            x
            for x in [
                str(r.get("selector_reasons") or "").strip(),
                f"Temas: {r.get('_temas_ui', '')}" if str(r.get("_temas_ui", "")).strip() else "",
                f"Entidades: {r.get('_entidades_ui', '')}" if str(r.get("_entidades_ui", "")).strip() else "",
                f"Regiones: {r.get('_regiones_ui', '')}" if str(r.get("_regiones_ui", "")).strip() else "",
            ]
            if x
        ),
        axis=1,
    )
    return out


def render_v6_search_briefing_app() -> None:
    st.title("Construye tu briefing")
    st.caption("Buscador V6 unificado: nacional + biz + regiones.")

    if st.button("Actualizar datos desde Supabase", use_container_width=False):
        _fetch_v6_corpus.clear()
        st.rerun()

    base_url, key = _supabase_config()

    try:
        with st.spinner("Cargando corpus V6 desde Supabase..."):
            df = _prep(_fetch_v6_corpus(base_url, key))
    except Exception as e:
        st.error(str(e))
        st.stop()

    if df.empty:
        st.warning("No hay artículos V6 en Supabase.")
        st.stop()

    min_date = df["article_date"].min()
    max_date = df["article_date"].max()
    if pd.isna(min_date) or pd.isna(max_date):
        min_date = max_date = date.today()

    previous_max_date = st.session_state.get("v6_corpus_max_date")
    date_from_state = st.session_state.get("v6_date_from")
    date_to_state = st.session_state.get("v6_date_to")
    if date_from_state is None or not min_date <= date_from_state <= max_date:
        st.session_state["v6_date_from"] = min_date
    if (
        date_to_state is None
        or not min_date <= date_to_state <= max_date
        or date_to_state == previous_max_date
    ):
        st.session_state["v6_date_to"] = max_date
    st.session_state["v6_corpus_max_date"] = max_date

    with st.sidebar:
        st.header("Buscar")
        date_from = st.date_input(
            "Desde", min_value=min_date, max_value=max_date, key="v6_date_from"
        )
        date_to = st.date_input(
            "Hasta", min_value=min_date, max_value=max_date, key="v6_date_to"
        )
        product_scope = st.selectbox("Producto", PRODUCTS, index=0)
        q = st.text_input(
            "Buscador",
            "",
            placeholder="Buscar tema, empresa, persona, entidad, región o título...",
        )

        st.header("Filtros")

    f = df.copy()
    f = f[(f["article_date"] >= date_from) & (f["article_date"] <= date_to)].copy()
    if product_scope != "Todos":
        f = f[f["product"].astype(str).eq(product_scope)].copy()
    if q.strip():
        f = f[f.apply(lambda row: _matches_search(row, q), axis=1)].copy()

    if f.empty:
        st.warning("No hay artículos para esa búsqueda.")
        st.stop()

    with st.sidebar:
        selected_temas = st.multiselect("Temas", _options(f, TEMA_COLS))
        selected_empresas = st.multiselect("Empresas / sector", _options(f, EMPRESA_SECTOR_COLS))
        selected_entidades = st.multiselect("Entidades", _options(f, ENTIDAD_COLS))
        selected_regiones = st.multiselect("Regiones", _options(f, REGION_COLS))

    f = f[f.apply(lambda r: _matches_selected(r, selected_temas, TEMA_COLS), axis=1)].copy()
    f = f[f.apply(lambda r: _matches_selected(r, selected_empresas, EMPRESA_SECTOR_COLS), axis=1)].copy()
    f = f[f.apply(lambda r: _matches_selected(r, selected_entidades, ENTIDAD_COLS), axis=1)].copy()
    f = f[f.apply(lambda r: _matches_selected(r, selected_regiones, REGION_COLS), axis=1)].copy()

    if f.empty:
        st.warning("No hay artículos para esos filtros.")
        st.stop()

    f = f.sort_values(["_score", "article_date", "outlet", "title"], ascending=[False, False, True, True]).reset_index(drop=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Filtrados", f"{len(f):,}")
    m2.metric("Corpus", f"{len(df):,}")
    m3.metric("Productos", f"{f['product'].nunique():,}")
    m4.metric("Medios", f"{f['outlet'].nunique():,}")

    left, right = st.columns([3, 1])

    with right:
        st.subheader("Formato")
        mode_one = st.checkbox("1-pager", value=True)
        mode_exec = st.checkbox("Resumen ejecutivo", value=False)
        mode_dossier = st.checkbox("Dossier", value=False)
        use_all_filtered = st.checkbox("Usar todos los filtrados", value=True)

        selected_modes: list[str] = []
        if mode_one:
            selected_modes.append("one_pager")
        if mode_exec:
            selected_modes.append("exec")
        if mode_dossier:
            selected_modes.append("dossier")

        run_btn = st.button("Arma tu briefing", type="primary", use_container_width=True)

    with left:
        st.subheader("Artículos")
        visible_source = f.copy().reset_index(drop=True)
        table = pd.DataFrame(
            {
                "Usar": [True] * len(visible_source),
                "Fecha": visible_source["article_date"].astype(str),
                "Producto": visible_source["product"].astype(str),
                "Medio": visible_source["outlet"].astype(str),
                "Título": visible_source["title"].astype(str),
                "Score": visible_source["_score"],
                "Temas": visible_source["_temas_ui"].astype(str),
                "Entidades": visible_source["_entidades_ui"].astype(str),
                "Regiones": visible_source["_regiones_ui"].astype(str),
            }
        )

        disabled = [c for c in table.columns if c != "Usar"]
        if use_all_filtered:
            table["Usar"] = True
            disabled = list(table.columns)

        edited = st.data_editor(
            table,
            hide_index=True,
            use_container_width=True,
            height=500,
            disabled=disabled,
            column_config={
                "Usar": st.column_config.CheckboxColumn("Usar"),
                "Fecha": st.column_config.TextColumn("Fecha"),
                "Producto": st.column_config.TextColumn("Producto"),
                "Medio": st.column_config.TextColumn("Medio"),
                "Título": st.column_config.TextColumn("Título", width="large"),
                "Score": st.column_config.NumberColumn("Score"),
                "Temas": st.column_config.TextColumn("Temas"),
                "Entidades": st.column_config.TextColumn("Entidades"),
                "Regiones": st.column_config.TextColumn("Regiones"),
            },
        )

    if use_all_filtered:
        selected_df = f.copy()
    else:
        selected_mask = edited["Usar"].fillna(False).astype(bool).to_list()
        selected_positions = [i for i, keep in enumerate(selected_mask) if keep]
        selected_df = visible_source.iloc[selected_positions].copy() if selected_positions else pd.DataFrame()

    st.write(f"Artículos seleccionados para briefing: **{len(selected_df)}**")

    if run_btn:
        if selected_df.empty:
            st.warning("Selecciona al menos un artículo.")
            st.stop()
        if not selected_modes:
            st.warning("Selecciona al menos un formato.")
            st.stop()

        st.session_state["v6_briefing_outputs"] = {}

        packet_df = _packet_source(selected_df)
        selected_rows = packet_df.to_dict("records")
        packet_date = str(date_from) if date_from == date_to else f"{date_from}_to_{date_to}"
        packet_product = product_scope if product_scope != "Todos" else "nacional+biz+regiones"
        selected_summary = {
            "Buscador": [q.strip()] if q.strip() else [],
            "Producto": [product_scope],
            "Temas": selected_temas,
            "Empresas / sector": selected_empresas,
            "Entidades": selected_entidades,
            "Regiones": selected_regiones,
            "Usa todos los filtrados": [str(use_all_filtered)],
        }

        for mode in selected_modes:
            spec = MODE_SPECS[mode]
            with st.spinner(f"Produciendo {spec['label']}..."):
                try:
                    packet = JasonMaker.build_packet(
                        selected_rows,
                        mode=mode,
                        max_input_chars=None,
                        max_articles=None,
                        snippet_chars=650,
                        target_chars=int(spec["target_chars"]),
                    )
                    packet["product"] = packet_product
                    packet["run_date"] = packet_date
                    packet["selected_filters"] = selected_summary
                    prompt = JasonMaker.make_prompt(packet)
                    raw = JasonMaker.call_flash(
                        prompt,
                        int(packet.get("target_output_chars") or spec["target_chars"]),
                        Path(".").resolve(),
                    )
                    final = repair_length(raw, mode, int(spec["max_chars"]))
                    base = f"v6_{packet_product}_{packet_date}_{mode}".replace("/", "-")
                    st.session_state["v6_briefing_outputs"][mode] = {
                        "label": spec["label"],
                        "markdown": final,
                        "chars": len(final),
                        "packet": packet,
                        "prompt": prompt,
                        "base": base,
                    }
                except Exception as e:
                    st.session_state["v6_briefing_outputs"][mode] = {
                        "label": spec["label"],
                        "error": str(e),
                    }

    outputs = st.session_state.get("v6_briefing_outputs", {})
    if outputs:
        st.divider()
        st.subheader("Briefings producidos")
        for mode, obj in outputs.items():
            st.markdown(f"### {obj.get('label', mode)}")
            if obj.get("error"):
                st.error(obj["error"])
                continue
            md = obj["markdown"]
            st.caption(f"{obj['chars']} caracteres")
            st.markdown(md)
            packet_obj = obj.get("packet", {}) or {}
            base = obj.get("base") or f"v6_{packet_obj.get('product', 'todos')}_{packet_obj.get('run_date', 'date')}_{mode}".replace("/", "-")
            d1, d2, d3 = st.columns(3)
            with d1:
                st.download_button("Descargar Markdown", md, file_name=f"{base}.md", mime="text/markdown", use_container_width=True)
            with d2:
                st.download_button(
                    "Descargar packet JSON",
                    json.dumps(obj["packet"], ensure_ascii=False, indent=2),
                    file_name=f"{base}_packet.json",
                    mime="application/json",
                    use_container_width=True,
                )
            with d3:
                st.download_button("Descargar prompt", obj["prompt"], file_name=f"{base}_prompt.txt", mime="text/plain", use_container_width=True)


if __name__ == "__main__":
    render_v6_search_briefing_app()


