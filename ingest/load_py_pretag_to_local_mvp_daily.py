#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


DEFAULT_PRETAG_ROOT = Path("/Users/mauricio/Projects/tagger_test")
DEFAULT_OUT = Path("/Users/mauricio/news_engine_tools/cloud_mvp/data/local_articles.csv")

DROP_CLASSES_DEFAULT = {
    "opinion_oped",
    "cartas",
    "deporte",
    "showbiz",
    "obituarios",
}


def clean(x):
    if x is None:
        return ""
    s = str(x)
    if s.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", s).strip()


def safe_json(obj):
    return json.dumps(obj, ensure_ascii=False)


def infer_date_scope(path):
    s = str(path)
    dm = re.search(r"(20\d{2}-\d{2}-\d{2})", s)
    date = dm.group(1) if dm else ""
    scope = ""
    parent = path.parent.name
    if parent.startswith(f"pretag_{date}_"):
        scope = parent.replace(f"pretag_{date}_", "")
    elif "nac-biz" in s:
        scope = "nac-biz"
    elif "_reg" in s or "regiones" in s:
        scope = "reg"
    return date, scope


def discover_inputs(root, date=None, scope=None):
    files = []
    for p in sorted(root.glob("pretag_20*/flash_input_20*.csv")):
        dt, sc = infer_date_scope(p)
        if date and dt != date:
            continue
        if scope and sc != scope:
            continue
        files.append((p, dt, sc))
    return files


def norm(x):
    s = clean(x).lower()
    for a, b in {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "ü": "u",
    }.items():
        s = s.replace(a, b)
    return s


def article_id_from(*parts):
    base = "|".join(clean(p) for p in parts)
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def tema_from_class_and_text(cls, title, section, text):
    hay = norm(" ".join([cls, title, section, text[:500]]))

    if "mineria" in hay or "codelco" in hay or "cobre" in hay or "litio" in hay or "sqm" in hay:
        return "Minería"
    if "energia" in hay or "electrico" in hay or "electricidad" in hay or "transelec" in hay:
        return "Energía"
    if "tecnologia" in hay or "inteligencia artificial" in hay or "ciberseguridad" in hay or "startup" in hay:
        return "Tecnología"
    if cls == "economia":
        return "Economía"
    if cls == "empresas":
        return "Empresas"
    if cls == "judicial_policial":
        return "Judicial"
    if cls == "salud":
        return "Política"
    if cls == "educacion":
        return "Política"
    if cls == "medio_ambiente":
        return "Medio ambiente"
    if cls == "regional":
        return "Regiones"
    if cls == "internacional":
        return "Política"
    return "Política"


def product_from_scope_and_class(scope, cls):
    if scope == "reg":
        return "regiones"
    if scope == "nac-biz":
        if cls in {"economia", "empresas", "mineria_energia"}:
            return "biz"
        return "nacional"
    return "nacional"


def regions_from_text(text):
    hay = norm(text)
    aliases = {
        "Arica y Parinacota": ["arica", "parinacota"],
        "Tarapacá": ["tarapaca", "iquique"],
        "Antofagasta": ["antofagasta", "calama"],
        "Atacama": ["atacama", "copiapo", "chanarcillo"],
        "Coquimbo": ["coquimbo", "la serena", "ovalle", "elqui", "limari"],
        "Valparaíso": ["valparaiso", "vina del mar", "viña del mar"],
        "Metropolitana": ["metropolitana", "santiago", "vitacura", "la florida"],
        "O'Higgins": ["ohiggins", "rancagua"],
        "Maule": ["maule", "talca"],
        "Ñuble": ["nuble", "chillan"],
        "Biobío": ["biobio", "bio bio", "concepcion", "concepción"],
        "La Araucanía": ["araucania", "temuco", "victoria"],
        "Los Ríos": ["los rios", "valdivia", "panguipulli", "rio bueno", "lanco", "paillaco"],
        "Los Lagos": ["los lagos", "puerto montt", "chiloe", "chiloé", "osorno"],
        "Aysén": ["aysen", "coyhaique"],
        "Magallanes": ["magallanes", "punta arenas", "tierra del fuego"],
    }
    found = []
    for region, keys in aliases.items():
        if any(k in hay for k in keys):
            found.append(region)
    return sorted(set(found))


def build_rows(path, date, scope, include_opinion):
    df = pd.read_csv(path, dtype=str, keep_default_na=False)

    rows = []
    for _, r in df.iterrows():
        d = {str(k): clean(v) for k, v in r.to_dict().items()}

        cls = d.get("pt_content_class", "")
        if not include_opinion and cls in DROP_CLASSES_DEFAULT:
            continue

        title = d.get("pt_title") or d.get("title")
        url = d.get("pt_url") or d.get("url")
        outlet = d.get("pt_outlet") or d.get("outlet") or d.get("source")
        article_date = d.get("pt_date") or date
        text = d.get("text") or d.get("pt_text_sample") or d.get("description") or ""
        section = d.get("pt_section", "")

        product = product_from_scope_and_class(scope, cls)
        tema = tema_from_class_and_text(cls, title, section, text)
        regions = regions_from_text(" ".join([title, outlet, section, text[:500]]))

        py_tags = {
            "temas": [tema],
            "empresas_sectores": [],
            "entidades": [],
            "regiones": regions,
            "pt_content_class": cls,
            "pt_info_tags": d.get("pt_info_tags", ""),
            "pt_keep_reason": d.get("pt_keep_reason", ""),
        }

        row_id = article_id_from(date, scope, product, url, title, d.get("pt_duplicate_key"), d.get("pt_source_row"))

        rows.append({
            "id": row_id,
            "article_id": row_id,
            "run_date": date,
            "article_date": article_date[:10] if article_date else date,
            "product": product,
            "source_scope": scope,
            "outlet": outlet,
            "title": title,
            "url": url,
            "text": text,
            "description": d.get("description", ""),
            "py_tags": safe_json(py_tags),
            "flash_tags": safe_json(py_tags),
            "tag_status": "py_pretagged",
            "tag_source": "python_pretagger",
            "tagger_model": "pretag_general_scrape.py",
            "briefing_relevance": "medium",
            "quality": "good" if not d.get("pt_quality_flags") else d.get("pt_quality_flags"),
            "noise_type": "none",
            "main_topic": cls,
            "entities": safe_json([]),
            "reason": d.get("pt_keep_reason", ""),
            "confidence": "1.0",
            "source_tag_file": str(path),
            "source_row_key": d.get("pt_duplicate_key", ""),
            "loaded_at": pd.Timestamp.utcnow().isoformat(),
        })

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pretag-root", default=str(DEFAULT_PRETAG_ROOT))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--date", default="", help="YYYY-MM-DD; omit to load all pretagged dates")
    ap.add_argument("--scope", default="", help="Optional: reg or nac-biz")
    ap.add_argument("--include-opinion", action="store_true")
    ap.add_argument("--rebuild", action="store_true")
    args = ap.parse_args()

    root = Path(args.pretag_root).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    inputs = discover_inputs(root, date=args.date or None, scope=args.scope or None)
    if not inputs:
        raise SystemExit(f"No pretag flash_input files found in {root} for date={args.date or '*'} scope={args.scope or '*'}")

    new_rows = []
    loaded_keys = []

    for path, date, scope in inputs:
        rows = build_rows(path, date, scope, args.include_opinion)
        new_rows.extend(rows)
        loaded_keys.append((date, scope))
        print(f"INPUT {path}")
        print(f"  loaded py_pretagged rows: {len(rows)}")

    new_df = pd.DataFrame(new_rows)
    if new_df.empty:
        raise SystemExit("No py_pretagged rows to load.")

    if out_path.exists() and out_path.stat().st_size > 0 and not args.rebuild:
        old_df = pd.read_csv(out_path, dtype=str, keep_default_na=False)
        keep = pd.Series([True] * len(old_df))

        for date, scope in loaded_keys:
            keep = keep & ~(
                (old_df.get("run_date", "").astype(str) == date)
                & (old_df.get("source_scope", "").astype(str) == scope)
            )

        backup = out_path.with_suffix(out_path.suffix + ".bak")
        old_df.to_csv(backup, index=False)
        final_df = pd.concat([old_df[keep].copy(), new_df], ignore_index=True, sort=False)
        print(f"BACKUP {backup}")
    else:
        final_df = new_df

    final_df = final_df.drop_duplicates(subset=["id"], keep="last")
    final_df.to_csv(out_path, index=False)

    print(f"OUT {out_path}")
    print(f"ROWS_WRITTEN {len(final_df)}")
    print("NEW_ROWS_BY_DATE_SCOPE_PRODUCT")
    print(new_df.groupby(["run_date", "source_scope", "product"]).size().to_string())


if __name__ == "__main__":
    main()
