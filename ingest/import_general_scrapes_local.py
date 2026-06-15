#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path

import pandas as pd


DEFAULT_ROOT = Path("/Users/mauricio/news_engine_tools/scrape_outlets/data/runs")
DEFAULT_OUT = Path("/Users/mauricio/news_engine_tools/cloud_mvp/data/local_articles.csv")


TAXONOMY = {
    "temas": [
        "Política", "Economía", "Empresas", "Minería", "Energía", "Seguridad",
        "Judicial", "Laboral", "Infraestructura", "Medio ambiente", "Tecnología", "Regiones"
    ],
    "empresas_sectores": [
        "Codelco", "SQM", "ENAP", "Enel", "Colbún", "CMPC", "Arauco", "BancoEstado",
        "Minería", "Energía", "Banca", "Retail", "Construcción", "Transporte",
        "Telecomunicaciones", "Salud", "Educación"
    ],
    "entidades": [
        "Gobierno", "Presidencia", "Congreso", "Senado", "Cámara de Diputados",
        "Ministerio de Hacienda", "Ministerio de Economía", "Ministerio de Minería",
        "Ministerio de Energía", "SEA", "CMF", "SII", "Tribunal Constitucional",
        "Corte Suprema", "Contraloría", "Fiscalía", "Banco Central"
    ],
    "regiones": [
        "Arica y Parinacota", "Tarapacá", "Antofagasta", "Atacama", "Coquimbo",
        "Valparaíso", "Metropolitana", "O'Higgins", "Maule", "Ñuble", "Biobío",
        "La Araucanía", "Los Ríos", "Los Lagos", "Aysén", "Magallanes"
    ],
}


KEYWORDS = {
    "temas": {
        "Política": ["gobierno", "presidente", "boric", "ministro", "ministra", "la moneda", "partido", "elección", "constitucional"],
        "Economía": ["economía", "inflación", "imacec", "pib", "hacienda", "presupuesto", "mercado", "dólar", "tasa", "banco central"],
        "Empresas": ["empresa", "compañía", "firma", "sociedad", "utilidades", "ventas", "ebitda", "inversión", "negocio"],
        "Minería": ["minería", "minero", "cobre", "litio", "codelco", "sqm", "faena"],
        "Energía": ["energía", "eléctrica", "electricidad", "hidrógeno", "solar", "eólico", "enel", "colbún"],
        "Seguridad": ["seguridad", "delito", "crimen", "homicidio", "robo", "carabinero", "pdi", "narco"],
        "Judicial": ["tribunal", "corte", "fiscalía", "querella", "demanda", "fallo", "juez", "formalización"],
        "Laboral": ["trabajadores", "sindicato", "huelga", "laboral", "empleo", "desempleo", "negociación colectiva"],
        "Infraestructura": ["infraestructura", "puente", "carretera", "metro", "puerto", "aeropuerto", "obra", "concesión"],
        "Medio ambiente": ["ambiental", "medio ambiente", "sea", "sma", "contaminación", "permiso ambiental", "evaluación ambiental"],
        "Tecnología": ["tecnología", "digital", "inteligencia artificial", "ia", "startup", "ciberseguridad", "datos"],
        "Regiones": ["región", "regional", "municipio", "alcalde", "gobernador regional"],
    },
    "empresas_sectores": {
        "Codelco": ["codelco"],
        "SQM": ["sqm", "sociedad química y minera"],
        "ENAP": ["enap"],
        "Enel": ["enel"],
        "Colbún": ["colbún", "colbun"],
        "CMPC": ["cmpc"],
        "Arauco": ["arauco"],
        "BancoEstado": ["bancoestado", "banco estado"],
        "Minería": ["minería", "cobre", "litio", "faena"],
        "Energía": ["energía", "eléctrica", "solar", "eólico", "hidrógeno"],
        "Banca": ["banco", "banca", "financiero"],
        "Retail": ["retail", "supermercado", "mall"],
        "Construcción": ["construcción", "inmobiliaria", "vivienda"],
        "Transporte": ["transporte", "metro", "tren", "bus", "puerto"],
        "Telecomunicaciones": ["telecom", "telefonía", "internet", "fibra"],
        "Salud": ["salud", "hospital", "clínica", "isapre", "fonasa"],
        "Educación": ["educación", "colegio", "universidad", "liceo"],
    },
    "entidades": {
        "Gobierno": ["gobierno"],
        "Presidencia": ["presidencia", "presidente boric", "la moneda"],
        "Congreso": ["congreso"],
        "Senado": ["senado", "senador"],
        "Cámara de Diputados": ["cámara de diputados", "diputado"],
        "Ministerio de Hacienda": ["ministerio de hacienda", "hacienda"],
        "Ministerio de Economía": ["ministerio de economía"],
        "Ministerio de Minería": ["ministerio de minería"],
        "Ministerio de Energía": ["ministerio de energía"],
        "SEA": ["servicio de evaluación ambiental", " sea ", "sea aprobó", "sea rechazó"],
        "CMF": ["cmf", "comisión para el mercado financiero"],
        "SII": ["sii", "servicio de impuestos internos"],
        "Tribunal Constitucional": ["tribunal constitucional"],
        "Corte Suprema": ["corte suprema"],
        "Contraloría": ["contraloría"],
        "Fiscalía": ["fiscalía", "ministerio público"],
        "Banco Central": ["banco central"],
    },
    "regiones": {
        "Arica y Parinacota": ["arica", "parinacota"],
        "Tarapacá": ["tarapacá", "iquique"],
        "Antofagasta": ["antofagasta", "calama"],
        "Atacama": ["atacama", "copiapó"],
        "Coquimbo": ["coquimbo", "la serena"],
        "Valparaíso": ["valparaíso", "valparaiso", "viña del mar"],
        "Metropolitana": ["metropolitana", "santiago", "rm"],
        "O'Higgins": ["o'higgins", "rancagua"],
        "Maule": ["maule", "talca"],
        "Ñuble": ["ñuble", "chillán"],
        "Biobío": ["biobío", "biobio", "concepción", "los ángeles"],
        "La Araucanía": ["araucanía", "araucania", "temuco"],
        "Los Ríos": ["los ríos", "valdivia"],
        "Los Lagos": ["los lagos", "puerto montt"],
        "Aysén": ["aysén", "aysen", "coyhaique"],
        "Magallanes": ["magallanes", "punta arenas"],
    },
}


def norm_text(*parts):
    raw = " ".join("" if x is None else str(x) for x in parts)
    raw = raw.lower()
    raw = re.sub(r"\s+", " ", raw)
    return f" {raw.strip()} "


def pick_matches(text, category):
    out = []
    for label, needles in KEYWORDS[category].items():
        for n in needles:
            if n.lower() in text:
                out.append(label)
                break
    return sorted(set(out))


def sha256_text(text):
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()


def derive_product(row, family):
    group = str(row.get("group", "") or "").strip().lower()
    zone = str(row.get("zone", "") or "").strip().lower()

    combined = f"{group} {zone} {family}".lower()

    if "reg" in combined:
        return "regiones"
    if "biz" in combined or "bizz" in combined or "business" in combined or "empresa" in combined:
        return "biz"
    if "nac" in combined or "nacional" in combined:
        return "nacional"

    return family


def find_input_files(root, dates):
    files = []
    for d in dates:
        day = root / d
        if not day.exists():
            print(f"MISS_DATE\t{day}")
            continue

        patterns = [
            "master_learned_v2_nac-biz-ex-useless/raw/articles_master_learned_v2_nac-biz_*.csv",
            "master_learned_v2_regiones-ex-useless/raw/articles_master_learned_v2_reg_*.csv",
        ]
        for pattern in patterns:
            for p in sorted(day.glob(pattern)):
                family = "regiones" if "_reg_" in p.name else "nac-biz"
                files.append((p, family))

    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--dates", nargs="+", default=None)
    ap.add_argument("--date", default="", help="Single YYYY-MM-DD date (alias for --dates DATE).")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--min-chars", type=int, default=80)
    args = ap.parse_args()

    root = Path(args.root)
    out = Path(args.out)
    dates = [args.date] if args.date else (args.dates or ["2026-06-13", "2026-06-14"])

    missing_dates = [d for d in dates if not (root / d).is_dir()]
    if missing_dates:
        raise SystemExit(f"Missing source directories for requested dates: {missing_dates}")

    files = find_input_files(root, dates)

    if not files:
        raise SystemExit("No input files found.")

    found_dates = {p.parts[p.parts.index("runs") + 1] for p, _ in files}
    missing_inputs = sorted(set(dates) - found_dates)
    if missing_inputs:
        raise SystemExit(f"No source CSV files found for requested dates: {missing_inputs}")

    frames = []

    print("INPUT_FILES")
    for p, family in files:
        print(f"{family}\t{p}")
        df = pd.read_csv(p)
        df["_input_file"] = str(p)
        df["_family"] = family
        frames.append(df)

    raw = pd.concat(frames, ignore_index=True)

    required = ["run_date", "group", "zone", "outlet", "url", "title", "description", "text", "word_count", "char_count"]
    missing = [c for c in required if c not in raw.columns]
    if missing:
        raise SystemExit(f"Missing required columns: {missing}")

    records = []
    for _, row in raw.iterrows():
        title = str(row.get("title", "") or "").strip()
        url = str(row.get("url", "") or "").strip()
        text_body = str(row.get("text", "") or "").strip()
        description = str(row.get("description", "") or "").strip()

        if not title:
            continue

        if len(text_body) < args.min_chars and len(description) < args.min_chars:
            continue

        family = str(row.get("_family", "") or "")
        product = derive_product(row, family)

        full_for_tagging = norm_text(title, description, text_body[:3000])

        py_tags = {
            "temas": pick_matches(full_for_tagging, "temas"),
            "empresas_sectores": pick_matches(full_for_tagging, "empresas_sectores"),
            "entidades": pick_matches(full_for_tagging, "entidades"),
            "regiones": pick_matches(full_for_tagging, "regiones"),
            "tagger": "local_keyword_v1"
        }

        # Local-only relevance heuristic. Flash can replace this later.
        relevance = 0
        relevance += min(len(py_tags["temas"]), 3)
        relevance += 1 if py_tags["empresas_sectores"] else 0
        relevance += 1 if py_tags["entidades"] else 0
        relevance = min(relevance, 5)

        body_sha = sha256_text(text_body or description or title)
        body_head_sha = sha256_text((text_body or description or title)[:2500])

        records.append({
            "article_id": row.get("article_id"),
            "run_date": row.get("run_date"),
            "article_date": row.get("published_date") or row.get("run_date"),
            "product": product,
            "raw_group": row.get("group"),
            "raw_zone": row.get("zone"),
            "source_family": family,
            "outlet": row.get("outlet"),
            "source": row.get("source"),
            "title": title,
            "url": url,
            "description": description,
            "text": text_body,
            "word_count": row.get("word_count"),
            "char_count": row.get("char_count"),
            "extraction_status": row.get("extraction_status"),
            "raw_snapshot_path": row.get("raw_snapshot_path"),
            "body_sha256": body_sha,
            "body_head_sha256": body_head_sha,
            "py_tags": json.dumps(py_tags, ensure_ascii=False),
            "flash_tags": json.dumps({}, ensure_ascii=False),
            "relevance_score": relevance,
            "tag_status": "py_only",
            "tag_source": "local_keyword_v1",
            "input_file": row.get("_input_file"),
        })

    out_df = pd.DataFrame(records)

    if out_df.empty:
        raise SystemExit("Importer produced zero rows after filters.")

    out_df = out_df.drop_duplicates(subset=["url"], keep="first")
    out.parent.mkdir(parents=True, exist_ok=True)
    out_df.to_csv(out, index=False)

    print("")
    print("OUTPUT", out)
    print("ROWS", len(out_df))
    print("")
    print("PRODUCT_COUNTS")
    print(out_df["product"].value_counts(dropna=False).to_string())
    print("")
    print("GROUP_COUNTS")
    print(out_df[["product", "raw_group", "source_family"]].value_counts(dropna=False).head(30).to_string())
    print("")
    print("TOP_OUTLETS")
    print(out_df["outlet"].value_counts(dropna=False).head(20).to_string())
    print("")
    print("TAG_STATUS")
    print(out_df["tag_status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()
