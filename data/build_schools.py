#!/usr/bin/env python3
"""
build_schools.py — IDF School Finder data pipeline
Produces data/schools.json from raw MENJ open data files.
Run: python3 data/build_schools.py
"""

import csv
import json
import os
import math
import re

RAW = os.path.join(os.path.dirname(__file__), "raw")
OUT = os.path.join(os.path.dirname(__file__), "schools.json")

IDF_DEPS = {"075", "077", "078", "091", "092", "093", "094", "095",
            "75", "77", "78", "91", "92", "93", "94", "95"}


# ── helpers ──────────────────────────────────────────────────────────────────

def csv_rows(filename, delim=";"):
    path = os.path.join(RAW, filename)
    if not os.path.exists(path):
        print(f"  MISSING: {path}")
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=delim))


def safe_float(val, default=None):
    if val is None:
        return default
    v = str(val).strip().replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return default


def parse_position(pos_str):
    """Parse 'lat, lon' string from annuaire position field."""
    if not pos_str:
        return None, None
    m = re.match(r"(-?\d+\.?\d*),\s*(-?\d+\.?\d*)", pos_str.strip())
    if m:
        return float(m.group(1)), float(m.group(2))
    return None, None


def percentile_rank(value, sorted_values):
    """Return 0–10 percentile rank of value within sorted_values list."""
    if not sorted_values or value is None:
        return None
    n = len(sorted_values)
    # Count how many are strictly below
    below = sum(1 for v in sorted_values if v < value)
    return round((below / n) * 10, 2)


def score_percentile(value, sorted_values):
    return percentile_rank(value, sorted_values)


# ── load & index data ─────────────────────────────────────────────────────────

def load_annuaire_idf():
    """Load IDF schools from full national annuaire."""
    print("Loading annuaire...")
    schools = {}
    for row in csv_rows("annuaire_national.csv"):
        dep = row.get("Code_departement", "").strip().lstrip("0")
        dep_padded = row.get("Code_departement", "").strip()
        if dep_padded not in IDF_DEPS and dep not in IDF_DEPS:
            continue
        uai = row.get("Identifiant_de_l_etablissement", "").strip()
        if not uai:
            continue
        lat, lon = parse_position(row.get("position", ""))
        nom = row.get("Nom_etablissement", "").strip()
        type_etab = row.get("Type_etablissement", "").strip()
        statut = row.get("Statut_public_prive", "").strip()
        type_contrat = row.get("Type_contrat_prive", "").strip()

        # Normalize statut
        if "Public" in statut or statut == "Public":
            secteur = "public"
        elif "contrat" in type_contrat.lower() or "Contrat" in statut:
            secteur = "prive_sous_contrat"
        elif "Privé" in statut or "Prive" in statut:
            secteur = "prive_hors_contrat"
        else:
            secteur = "public"

        # Level
        is_mat = row.get("Ecole_maternelle", "").strip() in ("1", "true", "True", "OUI")
        is_elem = row.get("Ecole_elementaire", "").strip() in ("1", "true", "True", "OUI")
        voie_g = row.get("Voie_generale", "").strip() in ("1", "true", "True", "OUI")
        voie_t = row.get("Voie_technologique", "").strip() in ("1", "true", "True", "OUI")
        voie_p = row.get("Voie_professionnelle", "").strip() in ("1", "true", "True", "OUI")

        type_lower = type_etab.lower()
        if "collège" in type_lower or "college" in type_lower:
            level = "college"
        elif "lycée" in type_lower or "lycee" in type_lower:
            level = "lycee"
        elif "ecole" in type_lower or "école" in type_lower:
            if is_mat and not is_elem:
                level = "maternelle"
            elif is_elem and not is_mat:
                level = "elementaire"
            else:
                level = "primaire"
        else:
            # Fallback from flags
            if voie_g or voie_t or voie_p:
                level = "lycee"
            elif is_mat and is_elem:
                level = "primaire"
            elif is_mat:
                level = "maternelle"
            elif is_elem:
                level = "elementaire"
            else:
                level = "other"

        if level == "other":
            continue

        code_commune = row.get("Code_commune", "").strip().zfill(5)
        dep_out = dep_padded.zfill(3).lstrip("0").zfill(2)

        # Extras from annuaire
        extras = {
            "section_sport": row.get("Section_sport", "").strip() in ("1", "OUI"),
            "section_arts": row.get("Section_arts", "").strip() in ("1", "OUI"),
            "section_internationale": row.get("Section_internationale", "").strip() in ("1", "OUI"),
            "section_europeenne": row.get("Section_europeenne", "").strip() in ("1", "OUI"),
            "section_cinema": row.get("Section_cinema", "").strip() in ("1", "OUI"),
            "section_theatre": row.get("Section_theatre", "").strip() in ("1", "OUI"),
            "ulis": row.get("ULIS", "").strip() in ("1", "OUI"),
            "segpa": row.get("Segpa", "").strip() in ("1", "OUI"),
            "rep": row.get("Appartenance_Education_Prioritaire", "").strip() in ("1", "OUI", "REP", "REP+"),
            "rep_label": row.get("Appartenance_Education_Prioritaire", "").strip(),
            "restauration": row.get("Restauration", "").strip() in ("1", "OUI"),
        }

        schools[uai] = {
            "uai": uai,
            "nom": nom,
            "type": type_etab,
            "level": level,
            "secteur": secteur,
            "adresse": " ".join(filter(None, [
                row.get("Adresse_1", "").strip(),
                row.get("Adresse_2", "").strip(),
                row.get("Adresse_3", "").strip(),
            ])),
            "code_postal": row.get("Code_postal", "").strip(),
            "commune": row.get("Nom_commune", "").strip(),
            "code_commune": code_commune,
            "dep": dep_out,
            "tel": row.get("Telephone", "").strip(),
            "web": row.get("Web", "").strip(),
            "mail": row.get("Mail", "").strip(),
            "fiche_onisep": row.get("Fiche_onisep", "").strip(),
            "lat": lat,
            "lon": lon,
            **extras,
        }
    print(f"  {len(schools)} IDF schools loaded")
    return schools


def load_ips_ecoles():
    """Load IPS for primary schools (2022+). Keep most recent per UAI."""
    print("Loading IPS écoles...")
    data = {}
    for row in csv_rows("ips_ecoles_primaires.csv"):
        uai = row.get("UAI", "").strip()
        rentree = row.get("Rentrée scolaire", "").strip()
        ips = safe_float(row.get("IPS", ""))
        if uai and ips is not None:
            if uai not in data or rentree > data[uai]["rentree"]:
                data[uai] = {"ips": ips, "rentree": rentree}
    print(f"  {len(data)} IPS écoles")
    return {k: v["ips"] for k, v in data.items()}


def load_ips_colleges():
    """Load IPS for collèges (2022+). Keep most recent per UAI."""
    print("Loading IPS collèges...")
    data = {}
    for fname in ["ips_colleges_ap2022.csv", "ips_colleges.csv"]:
        for row in csv_rows(fname):
            uai = row.get("UAI", "").strip()
            rentree = row.get("Rentrée scolaire", "").strip()
            ips = safe_float(row.get("IPS", ""))
            if uai and ips is not None:
                if uai not in data or rentree > data[uai]["rentree"]:
                    data[uai] = {"ips": ips, "rentree": rentree}
    print(f"  {len(data)} IPS collèges")
    return {k: v["ips"] for k, v in data.items()}


def load_ips_lycees():
    """Load IPS for lycées (2022+). Keep most recent per UAI."""
    print("Loading IPS lycées...")
    data = {}
    for row in csv_rows("ips_lycees.csv"):
        uai = row.get("UAI", "").strip()
        rentree = row.get("Rentrée scolaire", "").strip()
        ips_gt = safe_float(row.get("IPS voie GT", ""))
        ips_pro = safe_float(row.get("IPS voie PRO", ""))
        ips_ens = safe_float(row.get("IPS Ensemble GT-PRO", ""))
        ips = ips_ens or ips_gt or ips_pro
        if uai and ips is not None:
            if uai not in data or rentree > data[uai]["rentree"]:
                data[uai] = {"ips": ips, "ips_gt": ips_gt, "ips_pro": ips_pro, "rentree": rentree}
    print(f"  {len(data)} IPS lycées")
    return data


def load_lycee_gt():
    """Load lycée GT indicators. Keep most recent per UAI."""
    print("Loading lycée GT indicators...")
    data = {}
    for row in csv_rows("lycee_va_gt.csv"):
        uai = row.get("UAI", "").strip()
        annee = row.get("Annee", "").strip()
        if not uai:
            continue
        va_reussite = safe_float(row.get("Valeur ajoutee du taux de reussite - Toutes series", ""))
        va_mentions = safe_float(row.get("Valeur ajoutee du taux de mentions - Toutes series", ""))
        taux_reussite = safe_float(row.get("Taux de reussite - Toutes series", ""))

        # Mention rate: best available field
        # Count mentions B + TB from totals (général + technologique)
        pres = safe_float(row.get("Presents - Toutes series", ""))
        nb_b_g = safe_float(row.get("Nombre de mentions B - G", ""))
        nb_tb_fc_g = safe_float(row.get("Nombre de mentions TB avec félicitations - G", ""))
        nb_tb_sc_g = safe_float(row.get("Nombre de mentions TB sans félicitations - G", ""))
        nb_b_t = safe_float(row.get("Nombre de mentions B - T", ""))
        nb_tb_fc_t = safe_float(row.get("Nombre de mentions TB avec félicitations - T", ""))
        nb_tb_sc_t = safe_float(row.get("Nombre de mentions TB sans félicitations - T", ""))

        mention_rate = None
        nb_mentions_b_tb = sum(x for x in [nb_b_g, nb_tb_fc_g, nb_tb_sc_g, nb_b_t, nb_tb_fc_t, nb_tb_sc_t] if x is not None)
        if pres and pres > 0 and nb_mentions_b_tb > 0:
            mention_rate = round(nb_mentions_b_tb / pres * 100, 1)

        va = va_reussite if va_reussite is not None else va_mentions

        if uai not in data or str(annee) > str(data[uai]["annee"]):
            data[uai] = {
                "annee": annee,
                "taux_reussite": taux_reussite,
                "va": va,
                "va_reussite": va_reussite,
                "va_mentions": va_mentions,
                "mention_rate": mention_rate,
            }
    print(f"  {len(data)} lycée GT records")
    return data


def load_dnb():
    """Load DNB results per collège. Keep most recent session."""
    print("Loading DNB...")
    data = {}
    for row in csv_rows("dnb_par_etablissement.csv"):
        uai = row.get("Numero d'etablissement", "").strip()
        session = row.get("Session", "").strip()
        if not uai:
            continue
        presents = safe_float(row.get("Presents", ""))
        admis = safe_float(row.get("Admis", ""))
        mention_b = safe_float(row.get("Admis Mention bien", ""))
        mention_tb = safe_float(row.get("Admis Mention très bien", ""))
        taux_str = row.get("Taux de réussite", "").strip().replace("%", "").replace(",", ".")
        taux_reussite = safe_float(taux_str)

        mention_rate = None
        if presents and presents > 0:
            nb_b_tb = sum(x for x in [mention_b, mention_tb] if x is not None)
            if nb_b_tb > 0:
                mention_rate = round(nb_b_tb / presents * 100, 1)

        if uai not in data or session > data[uai]["session"]:
            data[uai] = {
                "session": session,
                "taux_reussite": taux_reussite,
                "mention_rate": mention_rate,
                "presents": presents,
            }
    print(f"  {len(data)} DNB records")
    return data


# ── scoring ───────────────────────────────────────────────────────────────────

def compute_scores(schools):
    """Add composite scores (0–10) using IDF percentile ranks."""

    # Collect IDF values by level for percentile computation
    ips_primaires = []
    ips_colleges = []
    ips_lycees = []
    dnb_mention_rates = []
    lycee_mention_rates = []
    lycee_va_vals = []

    for s in schools.values():
        lvl = s["level"]
        if lvl in ("maternelle", "elementaire", "primaire") and s.get("ips"):
            ips_primaires.append(s["ips"])
        elif lvl == "college" and s.get("ips"):
            ips_colleges.append(s["ips"])
            if s.get("dnb_mention_rate") is not None:
                dnb_mention_rates.append(s["dnb_mention_rate"])
        elif lvl == "lycee" and s.get("ips"):
            ips_lycees.append(s["ips"])
            if s.get("lycee_mention_rate") is not None:
                lycee_mention_rates.append(s["lycee_mention_rate"])
            if s.get("va") is not None:
                lycee_va_vals.append(s["va"])

    ips_primaires.sort()
    ips_colleges.sort()
    ips_lycees.sort()
    dnb_mention_rates.sort()
    lycee_mention_rates.sort()
    lycee_va_vals.sort()

    # VA normalization: clip to P5/P95, then scale 0–10
    if lycee_va_vals:
        p5_idx = max(0, int(len(lycee_va_vals) * 0.05))
        p95_idx = min(len(lycee_va_vals) - 1, int(len(lycee_va_vals) * 0.95))
        va_min = lycee_va_vals[p5_idx]
        va_max = lycee_va_vals[p95_idx]
    else:
        va_min, va_max = -5, 3

    def va_score(va):
        if va is None:
            return None
        clipped = max(va_min, min(va_max, va))
        if va_max == va_min:
            return 5.0
        return round((clipped - va_min) / (va_max - va_min) * 10, 2)

    for s in schools.values():
        lvl = s["level"]

        if lvl in ("maternelle", "elementaire", "primaire"):
            ips_score = score_percentile(s.get("ips"), ips_primaires)
            s["score"] = ips_score
            s["score_ips"] = ips_score

        elif lvl == "college":
            ips_score = score_percentile(s.get("ips"), ips_colleges)
            dnb_score = score_percentile(s.get("dnb_mention_rate"), dnb_mention_rates)
            s["score_ips"] = ips_score
            s["score_dnb"] = dnb_score
            if ips_score is not None and dnb_score is not None:
                s["score"] = round(0.7 * ips_score + 0.3 * dnb_score, 2)
            elif ips_score is not None:
                s["score"] = ips_score
            else:
                s["score"] = None

        elif lvl == "lycee":
            ips_score = score_percentile(s.get("ips"), ips_lycees)
            mention_score = score_percentile(s.get("lycee_mention_rate"), lycee_mention_rates)
            vs = va_score(s.get("va"))
            s["score_ips"] = ips_score
            s["score_mention"] = mention_score
            s["score_va"] = vs
            if ips_score is not None and mention_score is not None and vs is not None:
                s["score"] = round(0.5 * ips_score + 0.3 * mention_score + 0.2 * vs, 2)
            elif ips_score is not None and mention_score is not None:
                s["score"] = round(0.6 * ips_score + 0.4 * mention_score, 2)
            elif ips_score is not None:
                s["score"] = ips_score
            else:
                s["score"] = None
        else:
            s["score"] = None


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    print("=== Building schools.json ===")

    schools = load_annuaire_idf()

    ips_ecoles = load_ips_ecoles()
    ips_colleges = load_ips_colleges()
    ips_lycees_data = load_ips_lycees()
    lycee_gt = load_lycee_gt()
    dnb = load_dnb()

    # Join IPS
    print("Joining data...")
    matched_ips = 0
    for uai, s in schools.items():
        lvl = s["level"]
        if lvl in ("maternelle", "elementaire", "primaire"):
            ips = ips_ecoles.get(uai)
            if ips:
                s["ips"] = ips
                matched_ips += 1
        elif lvl == "college":
            ips = ips_colleges.get(uai)
            if ips:
                s["ips"] = ips
                matched_ips += 1
            # Join DNB
            dnb_rec = dnb.get(uai)
            if dnb_rec:
                s["dnb_taux_reussite"] = dnb_rec["taux_reussite"]
                s["dnb_mention_rate"] = dnb_rec["mention_rate"]
                s["dnb_session"] = dnb_rec["session"]
        elif lvl == "lycee":
            ips_rec = ips_lycees_data.get(uai)
            if ips_rec:
                s["ips"] = ips_rec["ips"]
                matched_ips += 1
            # Join lycée GT results
            gt_rec = lycee_gt.get(uai)
            if gt_rec:
                s["lycee_taux_reussite"] = gt_rec["taux_reussite"]
                s["lycee_mention_rate"] = gt_rec["mention_rate"]
                s["va"] = gt_rec["va"]
                s["va_reussite"] = gt_rec["va_reussite"]
                s["va_mentions"] = gt_rec["va_mentions"]
                s["lycee_annee"] = gt_rec["annee"]

    print(f"  IPS matched: {matched_ips}/{len(schools)}")

    # Compute scores
    print("Computing scores...")
    compute_scores(schools)

    # Build output list (drop schools without lat/lon)
    out = []
    no_coords = 0
    for s in schools.values():
        if s["lat"] is None or s["lon"] is None:
            no_coords += 1
            continue
        # Only keep schools with known levels
        if s["level"] == "other":
            continue
        # Clean output: remove None values to save space
        record = {k: v for k, v in s.items() if v is not None and v != "" and v is not False}
        # Always keep booleans that are True
        for k in ["section_sport", "section_arts", "section_internationale",
                  "section_europeenne", "section_cinema", "section_theatre",
                  "ulis", "segpa", "rep", "restauration"]:
            if s.get(k):
                record[k] = True
        out.append(record)

    print(f"  Kept: {len(out)} schools ({no_coords} dropped, no coordinates)")

    # Score stats
    scored = [s for s in out if s.get("score") is not None]
    print(f"  Scored: {len(scored)}/{len(out)}")

    # Write JSON
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = os.path.getsize(OUT) / 1024 / 1024
    print(f"\n✓ Written: {OUT} ({size_mb:.2f} MB, {len(out)} schools)")

    # Level breakdown
    from collections import Counter
    levels = Counter(s["level"] for s in out)
    secteurs = Counter(s["secteur"] for s in out)
    print(f"  Levels: {dict(levels)}")
    print(f"  Secteurs: {dict(secteurs)}")


if __name__ == "__main__":
    main()
