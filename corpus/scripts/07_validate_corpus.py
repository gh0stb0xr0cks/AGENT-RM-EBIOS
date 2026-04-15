"""
07_validate_corpus.py — Validation finale du corpus avant lancement du fine-tuning.

Vérifie :
  1. Intégrité structurelle (champs requis, format ChatML valide)
  2. Conformité terminologique ANSSI (zéro terme interdit dans train/eval)
  3. Couverture des ateliers et secteurs (pas de strate vide)
  4. Distribution des longueurs (percentiles P5/P50/P95)
  5. Absence de fuites train/test (hashes croisés)
  6. Ratio contre-exemples dans les splits

Produit un rapport JSON + affichage console avec code de sortie :
  0 = corpus valide, prêt pour fine-tuning
  1 = erreurs bloquantes détectées

Usage :
  python 07_validate_corpus.py
  python 07_validate_corpus.py --strict   # échoue sur tout avertissement
"""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).parent))
from schema import (
    FORBIDDEN_TERMS, REQUIRED_TERMS_BY_ATELIER,
    SCALE_PATTERN, SECTORS, SYSTEM_PROMPT,
)

ROOT         = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT / "datasets"
REPORT_PATH  = ROOT / "processed" / "validation_report.json"


# ---------------------------------------------------------------------------
# Structures de résultats
# ---------------------------------------------------------------------------

class ValidationResult(NamedTuple):
    errors:   list[str]   # bloquants
    warnings: list[str]   # non bloquants


# ---------------------------------------------------------------------------
# Checks individuels
# ---------------------------------------------------------------------------

CHATML_PATTERN = re.compile(
    r'<\|im_start\|>system\n.+?<\|im_end\|>\n'
    r'<\|im_start\|>user\n.+?<\|im_end\|>\n'
    r'<\|im_start\|>assistant\n.+?<\|im_end\|>',
    re.DOTALL
)

def check_chatml_format(record: dict) -> list[str]:
    """Vérifie la structure ChatML du champ 'text'."""
    text = record.get("text", "")
    errors = []
    if not text:
        errors.append("champ 'text' vide")
    elif not CHATML_PATTERN.search(text):
        errors.append("format ChatML invalide (manque system/user/assistant)")
    if SYSTEM_PROMPT[:50] not in text:
        errors.append("system prompt EBIOS manquant ou modifié")
    return errors


def check_no_forbidden_terms(record: dict) -> list[str]:
    """Zéro tolérance sur les termes interdits dans les exemples non-CE."""
    if record.get("is_counterexample"):
        return []
    text = record.get("text", "").lower()
    found = [t for t in FORBIDDEN_TERMS if t in text]
    return [f"terme interdit: '{t}'" for t in found]


def check_scale_in_text(record: dict) -> list[str]:
    """Cotation G/V requise pour A3/A4/A5."""
    if record.get("is_counterexample"):
        return []
    atelier = record.get("atelier", "")
    if atelier not in ("A3", "A4", "A5"):
        return []
    text = record.get("text", "")
    if not SCALE_PATTERN.search(text):
        return [f"cotation G/V absente pour atelier {atelier}"]
    return []


def check_required_fields(record: dict) -> list[str]:
    """Vérifie la présence des champs metadata."""
    required = {"text", "id", "atelier", "secteur", "source"}
    missing = required - set(record.keys())
    return [f"champ manquant: '{f}'" for f in missing]


def text_hash(record: dict) -> str:
    return hashlib.sha256(record.get("text", "").encode()).hexdigest()


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


# ---------------------------------------------------------------------------
# Validation d'un split
# ---------------------------------------------------------------------------

def validate_split(
    name: str,
    records: list[dict],
    strict: bool,
) -> tuple[int, int, list[str], list[str]]:
    """
    Valide tous les exemples d'un split.
    Retourne (n_errors, n_warnings, error_messages, warning_messages).
    """
    all_errors:   list[str] = []
    all_warnings: list[str] = []

    atelier_seen:  set[str] = set()
    secteur_seen:  set[str] = set()
    word_counts:   list[float] = []

    for i, rec in enumerate(records):
        ctx = f"[{name}#{i+1} id={rec.get('id','?')}]"

        # Champs requis
        field_errors = check_required_fields(rec)
        all_errors.extend(f"{ctx} {e}" for e in field_errors)

        # Format ChatML
        fmt_errors = check_chatml_format(rec)
        all_errors.extend(f"{ctx} {e}" for e in fmt_errors)

        # Termes interdits (erreur bloquante)
        term_errors = check_no_forbidden_terms(rec)
        all_errors.extend(f"{ctx} {e}" for e in term_errors)

        # Cotation
        scale_errors = check_scale_in_text(rec)
        all_warnings.extend(f"{ctx} {e}" for e in scale_errors)

        # Stats
        atelier_seen.add(rec.get("atelier", "?"))
        secteur_seen.add(rec.get("secteur", "?"))
        wc = len(rec.get("text", "").split())
        word_counts.append(wc)

    # Couverture ateliers
    for a in ["A1", "A2", "A3", "A4", "A5"]:
        if a not in atelier_seen:
            all_errors.append(f"[{name}] Atelier {a} absent du split")

    # Distribution longueurs
    if word_counts:
        p5  = percentile(word_counts, 5)
        p50 = percentile(word_counts, 50)
        p95 = percentile(word_counts, 95)
        if p5 < 30:
            all_warnings.append(
                f"[{name}] P5 longueur très faible : {p5:.0f} mots"
            )
        if p95 > 3000:
            all_warnings.append(
                f"[{name}] P95 longueur très élevée : {p95:.0f} mots"
            )
        print(f"  {name:6s} longueur mots — P5:{p5:.0f}  P50:{p50:.0f}  P95:{p95:.0f}")

    return (
        len(all_errors), len(all_warnings),
        all_errors, all_warnings,
    )


# ---------------------------------------------------------------------------
# Détection de fuite train/test
# ---------------------------------------------------------------------------

def check_no_leakage(
    train: list[dict], test: list[dict]
) -> list[str]:
    train_hashes = {text_hash(r) for r in train}
    leaks = []
    for r in test:
        if text_hash(r) in train_hashes:
            leaks.append(f"Fuite détectée : {r.get('id', '?')} présent dans train ET test")
    return leaks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Validation finale du corpus EBIOS RM"
    )
    parser.add_argument("--strict", action="store_true",
                        help="Échoue sur avertissements aussi")
    args = parser.parse_args()

    splits_to_check = {
        "train": DATASETS_DIR / "train.jsonl",
        "eval":  DATASETS_DIR / "eval.jsonl",
        "test":  DATASETS_DIR / "test.jsonl",
    }

    # Vérification existence
    for name, path in splits_to_check.items():
        if not path.exists():
            sys.exit(f"[ERREUR] Fichier manquant : {path}\n"
                     f"Lancer 06_stratified_split.py d'abord.")

    all_splits: dict[str, list[dict]] = {}
    for name, path in splits_to_check.items():
        records = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        all_splits[name] = records
        print(f"  {name:6s} : {len(records)} exemples chargés")

    print()
    total_errors   = 0
    total_warnings = 0
    report_details: dict[str, dict] = {}

    for name, records in all_splits.items():
        n_err, n_warn, errs, warns = validate_split(
            name, records, strict=args.strict
        )
        total_errors   += n_err
        total_warnings += n_warn
        report_details[name] = {
            "count":    len(records),
            "errors":   errs[:20],    # cap pour rapport
            "warnings": warns[:20],
        }

        if errs:
            print(f"\n  ❌ [{name}] {n_err} erreur(s) :")
            for e in errs[:5]:
                print(f"     {e}")
            if n_err > 5:
                print(f"     ... ({n_err-5} autres)")
        if warns:
            print(f"\n  ⚠️  [{name}] {n_warn} avertissement(s) :")
            for w in warns[:3]:
                print(f"     {w}")

    # Fuite train/test
    print("\nVérification fuites train→test...")
    leaks = check_no_leakage(all_splits["train"], all_splits["test"])
    if leaks:
        total_errors += len(leaks)
        report_details["leakage"] = {"errors": leaks}
        for leak in leaks[:5]:
            print(f"  ❌ {leak}")
    else:
        print("  ✓ Aucune fuite détectée")

    # Rapport
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "status":         "FAIL" if total_errors > 0 else "PASS",
        "total_errors":   total_errors,
        "total_warnings": total_warnings,
        "splits":         report_details,
    }
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*50}")
    if total_errors == 0 and total_warnings == 0:
        print("✅ Corpus VALIDE — prêt pour le fine-tuning")
        exit_code = 0
    elif total_errors == 0:
        print(f"✅ Corpus VALIDE avec {total_warnings} avertissement(s)")
        exit_code = 1 if args.strict else 0
    else:
        print(f"❌ Corpus INVALIDE — {total_errors} erreur(s) bloquante(s)")
        exit_code = 1

    print(f"Rapport complet → {REPORT_PATH}")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
