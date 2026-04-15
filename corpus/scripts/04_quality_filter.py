"""
04_quality_filter.py — Filtrage qualité multi-critères du corpus brut.

Critères de rejet :
  1. Terminologie interdite (termes ANSSI non conformes)
  2. Absence de cotation G/V pour les ateliers A3/A4/A5
  3. Absence de termes obligatoires par atelier
  4. Réponse trop courte (< 100 mots) ou trop longue (> 2 000 mots)
  5. Langue incorrecte (réponse non française détectée)
  6. Doublon exact (hash SHA-256 de la réponse)

Produit :
  - corpus/processed/filtered.jsonl     (exemples acceptés)
  - corpus/processed/rejected.jsonl     (exemples rejetés + raison)
  - corpus/processed/filter_report.json (statistiques)

Usage :
  python 04_quality_filter.py
  python 04_quality_filter.py --min-words 80 --max-words 1500
"""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import (
    FORBIDDEN_TERMS, REQUIRED_TERMS_BY_ATELIER,
    SCALE_PATTERN, CorpusExample,
)

ROOT = Path(__file__).resolve().parents[1]
RAW_SYNTHETICS = ROOT / "raw" / "synthetics"
PROCESSED_DIR  = ROOT / "processed"
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

FILTERED_PATH = PROCESSED_DIR / "filtered.jsonl"
REJECTED_PATH = PROCESSED_DIR / "rejected.jsonl"
REPORT_PATH   = PROCESSED_DIR / "filter_report.json"


# ---------------------------------------------------------------------------
# Règles de filtrage
# ---------------------------------------------------------------------------

def check_forbidden_terms(answer: str) -> list[str]:
    """Retourne la liste des termes interdits trouvés."""
    found = []
    answer_lower = answer.lower()
    for term in FORBIDDEN_TERMS:
        if term in answer_lower:
            found.append(term)
    return found


def check_required_terms(answer: str, atelier: str) -> list[str]:
    """Retourne les termes obligatoires manquants pour cet atelier."""
    required = REQUIRED_TERMS_BY_ATELIER.get(atelier, [])
    answer_lower = answer.lower()
    missing = [t for t in required if t.lower() not in answer_lower]
    return missing


def check_scale_present(answer: str, atelier: str) -> bool:
    """Vérifie la présence d'au moins une cotation G/V pour A3/A4/A5."""
    if atelier not in ("A3", "A4", "A5"):
        return True
    return bool(SCALE_PATTERN.search(answer))


def word_count(text: str) -> int:
    return len(text.split())


def answer_hash(answer: str) -> str:
    return hashlib.sha256(answer.strip().encode()).hexdigest()


def detect_non_french(text: str) -> bool:
    """Heuristique simple : présence de marqueurs anglais dominants."""
    english_markers = [
        " the ", " is ", " are ", " was ", " this ", " that ",
        " with ", " from ", " have ", " will ",
    ]
    text_lower = text.lower()
    count = sum(1 for m in english_markers if m in text_lower)
    return count >= 4


# ---------------------------------------------------------------------------
# Filtre principal
# ---------------------------------------------------------------------------

def filter_example(
    example: CorpusExample,
    min_words: int,
    max_words: int,
    seen_hashes: set[str],
) -> tuple[bool, list[str]]:
    """
    Retourne (accepté: bool, raisons_rejet: list[str]).
    Les contre-exemples passent TOUJOURS (ils sont volontairement incorrects).
    """
    if example.is_counterexample:
        return True, []

    # Récupère le contenu de la réponse assistant
    assistant_msgs = [m for m in example.messages if m.role == "assistant"]
    if not assistant_msgs:
        return False, ["no_assistant_message"]

    answer = assistant_msgs[0].content
    reasons: list[str] = []

    # 1. Termes interdits
    forbidden = check_forbidden_terms(answer)
    if forbidden:
        reasons.append(f"forbidden_terms:{','.join(forbidden)}")

    # 2. Cotation G/V manquante
    if not check_scale_present(answer, example.atelier):
        reasons.append("missing_scale")

    # 3. Termes obligatoires manquants
    missing = check_required_terms(answer, example.atelier)
    if len(missing) == len(REQUIRED_TERMS_BY_ATELIER.get(example.atelier, [])):
        # Rejet seulement si AUCUN terme requis n'est présent
        reasons.append(f"missing_required_terms:{','.join(missing[:3])}")

    # 4. Longueur
    wc = word_count(answer)
    if wc < min_words:
        reasons.append(f"too_short:{wc}_words")
    elif wc > max_words:
        reasons.append(f"too_long:{wc}_words")

    # 5. Langue
    if detect_non_french(answer):
        reasons.append("non_french")

    # 6. Doublon
    h = answer_hash(answer)
    if h in seen_hashes:
        reasons.append("duplicate")
    else:
        seen_hashes.add(h)

    return len(reasons) == 0, reasons


# ---------------------------------------------------------------------------
# Chargement du corpus brut
# ---------------------------------------------------------------------------

def load_all_raw() -> list[CorpusExample]:
    """Charge tous les JSONL depuis raw/synthetics/."""
    examples: list[CorpusExample] = []
    jsonl_files = sorted(RAW_SYNTHETICS.glob("*.jsonl"))

    if not jsonl_files:
        print(f"[WARN] Aucun fichier JSONL dans {RAW_SYNTHETICS}")
        return []

    for path in jsonl_files:
        print(f"  Chargement : {path.name}")
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    examples.append(CorpusExample.from_dict(d))
                except Exception as e:
                    print(f"    [WARN] Ligne {lineno} ignorée : {e}")

    return examples


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Filtrage qualité du corpus EBIOS RM"
    )
    parser.add_argument("--min-words", type=int, default=80)
    parser.add_argument("--max-words", type=int, default=2000)
    args = parser.parse_args()

    print("Chargement du corpus brut...")
    examples = load_all_raw()
    print(f"  {len(examples)} exemples chargés\n")

    seen_hashes: set[str] = set()
    accepted: list[CorpusExample] = []
    rejected: list[tuple[CorpusExample, list[str]]] = []

    rejection_counts: dict[str, int] = defaultdict(int)

    for ex in examples:
        ok, reasons = filter_example(
            ex,
            min_words=args.min_words,
            max_words=args.max_words,
            seen_hashes=seen_hashes,
        )
        if ok:
            accepted.append(ex)
        else:
            rejected.append((ex, reasons))
            for r in reasons:
                # Normalise la raison (supprime les détails après ':')
                key = r.split(":")[0]
                rejection_counts[key] += 1

    # Sauvegarde
    with open(FILTERED_PATH, "w", encoding="utf-8") as f:
        for ex in accepted:
            f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")

    with open(REJECTED_PATH, "w", encoding="utf-8") as f:
        for ex, reasons in rejected:
            record = ex.to_dict()
            record["rejection_reasons"] = reasons
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    # Rapport
    total = len(examples)
    n_acc = len(accepted)
    n_rej = len(rejected)

    # Distribution par atelier (acceptés)
    atelier_dist: dict[str, int] = defaultdict(int)
    secteur_dist:  dict[str, int] = defaultdict(int)
    for ex in accepted:
        atelier_dist[ex.atelier] += 1
        secteur_dist[ex.secteur]  += 1

    report = {
        "total_input":      total,
        "accepted":         n_acc,
        "rejected":         n_rej,
        "acceptance_rate":  round(n_acc / total * 100, 1) if total else 0,
        "rejection_by_reason": dict(sorted(rejection_counts.items(),
                                           key=lambda x: -x[1])),
        "accepted_by_atelier": dict(sorted(atelier_dist.items())),
        "accepted_by_secteur": dict(sorted(secteur_dist.items())),
    }

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Affichage
    print(f"Résultats du filtrage :")
    print(f"  Acceptés  : {n_acc:>5} / {total} ({report['acceptance_rate']}%)")
    print(f"  Rejetés   : {n_rej:>5}")
    print(f"\nRaisons de rejet :")
    for reason, count in report["rejection_by_reason"].items():
        print(f"  {reason:30s} : {count}")
    print(f"\nDistribution par atelier :")
    for atelier, count in report["accepted_by_atelier"].items():
        print(f"  {atelier} : {count}")
    print(f"\nRapport complet → {REPORT_PATH}")


if __name__ == "__main__":
    main()
