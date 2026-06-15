#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


DEFAULT_TAGS_DIR = Path("/Users/mauricio/Projects/tagger_test/tags")
DEFAULT_OUT = Path("/Users/mauricio/news_engine_tools/cloud_mvp/data/local_articles.csv")


CONTROLLED_TEMAS = [
    "Política", "Economía", "Empresas", "Minería", "Energía", "Seguridad",
    "Judicial", "Laboral", "Infraestructura", "Medio ambiente", "Tecnología", "Regiones"
]

CHILE_REGIONS = [
    "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
    "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble", "Biobío",
    "La Araucanía", "Los Ríos", "Los Lagos", "Aysén", "Magallanes"
]


def clean(x):
    if x is None:
        return ""
    s = str(x)
    if s.lower() == "nan":
        return ""
    return re.sub(r"\s+", " ", s).strip()


def norm(x):
    s = clean(x).lower()
    repl = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ñ": "n", "ü": "u",
    }
    for a, b in repl.items():
        s = s.replace(a, b)
    return s


def parse_bool(x):
    s = clean(x).lower()
    return s in {"true", "1", "yes", "si", "sí"}


def parse_json_list(x):
    s = clean(x)
    if not s:
        return []
    try:
        obj = json.loads(s)
        if isinstance(obj, list):
            return [clean(v) for v in obj if clean(v)]
        if isinstance(obj, str):
            return [clean(obj)] if clean(obj) else []
    except Exception:
        pass
    return [v.strip() for v in s.split(";") if v.strip()]


def safe_json(obj):
    return json.dumps(obj, ensure_ascii=False)


def infer_scope_date(path):
    m = re.search(r"tagged_articles_master_learned_v2_(.+)_(20\d{2}-\d{2}-\d{2})\.csv$", path.name)
    if not m:
        return None, None
    return m.group(1), m.group(2)


def discover_tag_files(tags_dir, date=None, scope=None):
    out = []
    for p in sorted(tags_dir.glob("tagged_articles_master_learned_v2_*_20*.csv")):
        sc, dt = infer_scope_date(p)
        if not sc or not dt:
            continue
        if date and dt != date:
            continue
        if scope and sc != scope:
            continue
        out.append((p, sc, dt))
    return out


def source_row_lookup(source_file):
    """
    Flash tagger output only carries selected source fields.
    This reads the pretag flash_input CSV pointed to by source_file
    so local app rows can keep text/sample/context.
    """
    p = Path(clean(source_file))
    if not p.exists():
        return {}

    try:
        df = pd.read_csv(p, dtype=str, keep_default_na=False)
    except Exception:
        return {}

    lookup = {}
    for idx, row in df.iterrows():
        d = {str(k): clean(v) for k, v in row.to_dict().items()}
        lookup[str(idx)] = d
    return lookup


def controlled_tema(main_topic, product, title, reason, entities):
    hay = norm(" ".join([main_topic, product, title, reason, " ".join(entities)]))

    checks = [
        ("Minería", ["mineria", "minera", "codelco", "sqm", "litio", "cobre", "enami"]),
        ("Energía", ["energia", "electrico", "electricidad", "transelec", "enel", "colbun", "hidrogeno"]),
        ("Tecnología", ["tecnologia", "inteligencia artificial", " ciber", "startup", "robot", "nasa", "digital", "data center"]),
        ("Economía", ["economia", "inflacion", "imacec", "banco central", "tasa", "dolar", "mercado", "empleo", "tribut"]),
        ("Empresas", ["empresa", "walmart", "redsalud", "negocio", "inversion", "expansion", "ventas", "utilidades"]),
        ("Seguridad", ["seguridad", "delito", "homicidio", "asalto", "robo", "carabineros", "pdi", "tren de aragua"]),
        ("Judicial", ["tribunal", "corte", "fiscalia", "querella", "juicio", "formalizacion", "contraloria"]),
        ("Laboral", ["laboral", "trabajadores", "sindicato", "huelga", "negociacion colectiva"]),
        ("Infraestructura", ["ruta", "concesion", "puerto", "aeropuerto", "metro", "carretera", "obra publica", "mop"]),
        ("Medio ambiente", ["ambiental", "sma", "sea", "desaladora", "contaminacion", "salmuera", "evaluacion ambiental"]),
        ("Política", ["gobierno", "presidente", "congreso", "senado", "diputado", "ministro", "alcalde", "gobernador"]),
        ("Regiones", ["regional", "region", "municipalidad", "comuna", "vecinos"]),
    ]

    for label, needles in checks:
        if any(n in hay for n in needles):
            return label

    if product == "biz":
        return "Empresas"
    if product == "regiones":
        return "Regiones"
    if product == "nacional":
        return "Política"

    return "Política"


def infer_regions(title, entities, source_extra):
    hay = norm(" ".join([title, " ".join(entities), source_extra]))
    found = []

    aliases = {
        "Arica y Parinacota": ["arica", "parinacota"],
        "Tarapacá": ["tarapaca", "iquique"],
        "Antofagasta": ["antofagasta", "calama"],
        "Atacama": ["atacama", "copiapo", "chanarcillo"],
        "Coquimbo": ["coquimbo", "la serena", "ovalle", "elqui", "limari"],
        "Valparaíso": ["valparaiso", "vina del mar", "viña del mar"],
        "Metropolitana": ["metropolitana", "santiago", "la florida", "vitacura"],
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

    for region, keys in aliases.items():
        if any(k in hay for k in keys):
            found.append(region)

    return sorted(set(found))


def article_id_from(*parts):
    base = "|".join(clean(p) for p in parts)
    return hashlib.sha1(base.encode("utf-8", errors="ignore")).hexdigest()[:16]


def accepted_rows(df):
    out = df.copy()

    if "discard" in out.columns:
        out = out[out["discard"].apply(lambda x: not parse_bool(x))]

    if "is_news_article" in out.columns:
        out = out[out["is_news_article"].apply(parse_bool)]

    if "quality" in out.columns:
        bad_quality = {"broken", "listing", "non_article", "paywall_stub"}
        out = out[~out["quality"].astype(str).str.lower().isin(bad_quality)]

    if "briefing_relevance" in out.columns:
        out = out[out["briefing_relevance"].astype(str).str.lower() != "discard"]

    return out.copy()


def build_local_rows(tag_path, scope, date):
    tag_df = pd.read_csv(tag_path, dtype=str, keep_default_na=False)
    tag_df = accepted_rows(tag_df)

    source_cache = {}
    rows = []

    for _, r in tag_df.iterrows():
        source_file = clean(r.get("source_file", ""))
        source_row_index = clean(r.get("source_row_index", ""))

        if source_file not in source_cache:
            source_cache[source_file] = source_row_lookup(source_file)
        src = source_cache[source_file].get(source_row_index, {})

        product_fit = [norm(x) for x in parse_json_list(r.get("product_fit", ""))]
        products = [p for p in product_fit if p in {"nacional", "biz", "regiones"}]

        if not products and scope == "reg":
            products = ["regiones"]

        if not products:
            continue

        title = clean(r.get("src_title")) or clean(src.get("pt_title")) or clean(src.get("title"))
        url = clean(r.get("src_url")) or clean(src.get("pt_url")) or clean(src.get("url"))
        outlet = clean(r.get("src_outlet")) or clean(src.get("pt_outlet")) or clean(src.get("outlet")) or clean(src.get("source"))
        article_date = clean(r.get("src_published_date")) or clean(r.get("src_date")) or clean(src.get("pt_date")) or date

        text = (
            clean(src.get("text"))
            or clean(src.get("body"))
            or clean(src.get("content"))
            or clean(src.get("pt_text_sample"))
            or clean(src.get("description"))
            or clean(r.get("reason"))
        )

        main_topic = clean(r.get("main_topic"))
        reason = clean(r.get("reason"))
        entities = parse_json_list(r.get("entities", ""))

        regions = infer_regions(title, entities, " ".join([
            clean(src.get("pt_section")),
            clean(src.get("pt_domain")),
            clean(src.get("pt_outlet")),
        ]))

        for product in products:
            tema = controlled_tema(main_topic, product, title, reason, entities)

            flash_tags = {
                "temas": [tema],
                "empresas_sectores": entities if product == "biz" else [],
                "entidades": entities,
                "regiones": regions,
                "model_main_topic": main_topic,
                "product_fit": products,
                "briefing_relevance": clean(r.get("briefing_relevance")),
                "quality": clean(r.get("quality")),
                "noise_type": clean(r.get("noise_type")),
                "confidence": clean(r.get("confidence")),
                "reason": reason,
            }

            row_id = article_id_from(date, product, scope, url, title, clean(r.get("source_row_key")))

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
                "description": clean(src.get("description")),
                "py_tags": safe_json({}),
                "flash_tags": safe_json(flash_tags),
                "tag_status": "flash_done",
                "tag_source": "google_gemini",
                "tagger_model": clean(r.get("tagger_model")),
                "briefing_relevance": clean(r.get("briefing_relevance")),
                "quality": clean(r.get("quality")),
                "noise_type": clean(r.get("noise_type")),
                "main_topic": main_topic,
                "entities": safe_json(entities),
                "reason": reason,
                "confidence": clean(r.get("confidence")),
                "source_tag_file": str(tag_path),
                "source_row_key": clean(r.get("source_row_key")),
                "loaded_at": pd.Timestamp.utcnow().isoformat(),
            })

    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tags-dir", default=str(DEFAULT_TAGS_DIR))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--date", default="", help="YYYY-MM-DD. If omitted, load all discovered dates.")
    ap.add_argument("--scope", default="", help="Optional: reg or nac-biz")
    ap.add_argument("--rebuild", action="store_true", help="Ignore existing local CSV and rebuild from discovered tag files.")
    args = ap.parse_args()

    tags_dir = Path(args.tags_dir).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = discover_tag_files(tags_dir, date=args.date or None, scope=args.scope or None)
    if not files:
        raise SystemExit(f"No tagged files found in {tags_dir} for date={args.date or '*'} scope={args.scope or '*'}")

    new_rows = []
    loaded_keys = []

    for tag_path, scope, date in files:
        rows = build_local_rows(tag_path, scope, date)
        new_rows.extend(rows)
        loaded_keys.append((date, scope))
        print(f"INPUT {tag_path}")
        print(f"  accepted local rows: {len(rows)}")

    new_df = pd.DataFrame(new_rows)

    if new_df.empty:
        raise SystemExit("No accepted Flash rows to load.")

    if out_path.exists() and out_path.stat().st_size > 0 and not args.rebuild:
        old_df = pd.read_csv(out_path, dtype=str, keep_default_na=False)
        keep = pd.Series([True] * len(old_df))

        for date, scope in loaded_keys:
            if "run_date" in old_df.columns and "source_scope" in old_df.columns:
                keep = keep & ~(
                    (old_df["run_date"].astype(str) == date)
                    & (old_df["source_scope"].astype(str) == scope)
                )

        final_df = pd.concat([old_df[keep].copy(), new_df], ignore_index=True, sort=False)
        backup = out_path.with_suffix(out_path.suffix + ".bak")
        old_df.to_csv(backup, index=False)
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
