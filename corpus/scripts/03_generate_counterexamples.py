"""
03_generate_counterexamples.py — Génération de contre-exemples annotés.

Les contre-exemples sont des réponses délibérément incorrectes avec annotation
de l'erreur. Ils servent à deux usages :
  1. Fine-tuning DPO/RLHF (rejected samples)
  2. Évaluation du garde-fou terminologique

Types d'erreurs simulées :
  - forbidden_term     : utilisation d'un terme interdit (ex: "menaces")
  - wrong_scale        : cotation hors échelle (ex: "niveau 3" au lieu de "G3")
  - wrong_methodology  : confusion avec ISO 27005 ou EBIOS 2010
  - incomplete_answer  : réponse tronquée sans cotation pour A3/A4/A5
  - hallucinated_rule  : invention d'une règle EBIOS RM inexistante

Produit : corpus/raw/synthetics/counterexamples.jsonl

Usage :
  python 03_generate_counterexamples.py --count 200
  python 03_generate_counterexamples.py --error-type forbidden_term --count 50
"""
from __future__ import annotations
import argparse
import json
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import (
    FORBIDDEN_TERMS, SECTORS, ATELIERS,
    CorpusExample, Message,
)

ROOT = Path(__file__).resolve().parents[1]
SYNTHETICS_DIR = ROOT / "raw" / "synthetics"
SYNTHETICS_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = SYNTHETICS_DIR / "counterexamples.jsonl"


# ---------------------------------------------------------------------------
# Mutations d'erreur
# ---------------------------------------------------------------------------

def inject_forbidden_term(answer: str) -> tuple[str, str]:
    """Remplace un terme ANSSI par son équivalent interdit."""
    replacements = {
        "valeurs métier":            "biens essentiels",
        "biens supports":            "actifs",
        "sources de risque":         "menaces",
        "plan de traitement du risque": "PACS",
        "risque résiduel":           "risque net",
        "risque initial":            "risque brut",
    }
    for correct, wrong in replacements.items():
        if correct in answer:
            mutated = answer.replace(correct, wrong, 1)
            return mutated, "forbidden_term"
    # Fallback : injection directe
    mutated = answer + "\n\nLes menaces identifiées sont prioritaires."
    return mutated, "forbidden_term"


def inject_wrong_scale(answer: str) -> tuple[str, str]:
    """Remplace une cotation G/V par une notation erronée."""
    import re
    # Remplace G3 → "niveau 3", V2 → "vraisemblance 2"
    mutated = re.sub(r'\bG([1-4])\b', r'niveau \1', answer)
    mutated = re.sub(r'\bV([1-4])\b', r'vraisemblance \1', mutated)
    if mutated == answer:
        mutated = answer + "\n\nLe niveau de risque est estimé à 3/5."
    return mutated, "wrong_scale"


def inject_wrong_methodology(answer: str) -> tuple[str, str]:
    """Insère une confusion avec ISO 27005 ou EBIOS 2010."""
    confusion_phrases = [
        "\n\nConformément à l'approche ISO 27005, les biens essentiels sont classifiés "
        "selon leur criticité métier.",
        "\n\nSelon EBIOS 2010, les événements redoutés sont cotés de 1 à 4.",
        "\n\nL'analyse des risques résiduels s'appuie sur la matrice EBIOS classique "
        "(vraisemblance × impact).",
        "\n\nLes actifs informationnels sont identifiés conformément à l'ISO/IEC 27001.",
    ]
    mutated = answer + random.choice(confusion_phrases)
    return mutated, "wrong_methodology"


def inject_incomplete_answer(answer: str) -> tuple[str, str]:
    """Tronque la réponse avant les éléments de cotation."""
    import re
    # Coupe avant toute mention de cotation
    cut_point = re.search(r'\b(Gravité|Vraisemblance|G[1-4]|V[1-4]|cotation)', answer)
    if cut_point:
        mutated = answer[:cut_point.start()].rstrip()
        mutated += "\n\n[La cotation sera définie ultérieurement.]"
    else:
        mutated = answer[:len(answer)//2] + "\n\n[À compléter.]"
    return mutated, "incomplete_answer"


def inject_hallucinated_rule(answer: str) -> tuple[str, str]:
    """Ajoute une règle EBIOS RM inventée."""
    hallucinations = [
        "\n\nNote : selon l'annexe C de la méthode EBIOS RM, tout scénario "
        "stratégique doit obligatoirement être validé par un tiers certificateur.",
        "\n\nL'ANSSI impose un délai maximum de 30 jours entre l'atelier 3 et "
        "l'atelier 4 pour maintenir la cohérence de l'analyse.",
        "\n\nConformément au guide EBIOS RM 2024, la dangerosité minimale requise "
        "pour qu'une partie prenante soit retenue est de 2,5.",
        "\n\nLe RGS impose que toute analyse EBIOS RM soit conduite par un "
        "prestataire qualifié PASSI de niveau 2 minimum.",
    ]
    mutated = answer + random.choice(hallucinations)
    return mutated, "hallucinated_rule"


MUTATION_FUNCTIONS = {
    "forbidden_term":     inject_forbidden_term,
    "wrong_scale":        inject_wrong_scale,
    "wrong_methodology":  inject_wrong_methodology,
    "incomplete_answer":  inject_incomplete_answer,
    "hallucinated_rule":  inject_hallucinated_rule,
}


# ---------------------------------------------------------------------------
# Exemples sources pour mutation (base minimale intégrée)
# ---------------------------------------------------------------------------

BASE_EXAMPLES = [
    {
        "atelier": "A3",
        "secteur": "sante",
        "question": "Construis un scénario stratégique pour un CHU ciblé par ransomware.",
        "answer": (
            "Scénario stratégique SS-01 : Chiffrement du SI hospitalier par ransomware.\n\n"
            "Source de risque : groupe cybercriminel organisé.\n"
            "Objectif visé : extorsion financière via interruption des soins.\n"
            "Valeurs métier ciblées : prise en charge des patients, DPI.\n"
            "Biens supports visés : serveurs applicatifs, PACS, réseau interne.\n"
            "Vraisemblance : V3 — Très vraisemblable.\n"
            "Gravité : G4 — Critique (risque vital pour les patients).\n"
            "Niveau de risque initial : Critique."
        ),
    },
    {
        "atelier": "A2",
        "secteur": "finance",
        "question": "Quelles sources de risque prioriser pour une banque de détail ?",
        "answer": (
            "Les sources de risque prioritaires pour une banque de détail sont :\n\n"
            "SR1 — Cybercriminel organisé / Objectif visé : ransomware ou vol de données.\n"
            "SR2 — Insider malveillant / Objectif visé : fraude interne ou revente de données.\n"
            "SR3 — État étranger hostile / Objectif visé : déstabilisation du système financier.\n\n"
            "La pertinence de chaque source de risque est évaluée au regard des "
            "valeurs métier et biens supports identifiés en atelier 1."
        ),
    },
    {
        "atelier": "A1",
        "secteur": "energie",
        "question": "Identifier les biens supports critiques d'un opérateur de réseau électrique.",
        "answer": (
            "Pour la valeur métier 'distribution électrique', les biens supports critiques sont :\n\n"
            "- Systèmes SCADA de conduite du réseau (EMS/SCADA)\n"
            "- Postes de transformation téléopérés\n"
            "- Réseau de télécommunications de contrôle-commande\n"
            "- Centres de dispatching régionaux\n"
            "- Systèmes de comptage communicant (smart meters)\n\n"
            "Le besoin de sécurité dominant est la Disponibilité (DICP), "
            "toute interruption ayant un impact direct sur la continuité de service."
        ),
    },
    {
        "atelier": "A5",
        "secteur": "administration",
        "question": "Comment structurer le plan de traitement du risque pour un ministère ?",
        "answer": (
            "Le plan de traitement du risque intègre pour chaque scénario retenu :\n\n"
            "1. Stratégie de traitement : réduction, transfert, acceptation ou refus.\n"
            "2. Mesures techniques : segmentation réseau, EDR, chiffrement, MFA.\n"
            "3. Mesures organisationnelles : habilitations, formation, PCA/PRA.\n"
            "4. Risque résiduel après mesures : cotation G/V résiduelle.\n"
            "5. Responsable et échéance de mise en œuvre.\n\n"
            "Le dossier d'homologation compile l'ensemble des risques résiduels "
            "pour décision de l'autorité d'homologation."
        ),
    },
]


# ---------------------------------------------------------------------------
# Génération des contre-exemples
# ---------------------------------------------------------------------------

def generate_counterexample(
    base: dict,
    error_type: str,
) -> CorpusExample:
    """Applique une mutation d'erreur sur un exemple de base."""
    mutate_fn = MUTATION_FUNCTIONS[error_type]
    mutated_answer, confirmed_type = mutate_fn(base["answer"])

    example_id = f"ce_{base['secteur']}_{base['atelier'].lower()}_{uuid.uuid4().hex[:6]}"

    return CorpusExample(
        id=example_id,
        atelier=base["atelier"],
        secteur=base["secteur"],
        source="counterexample",
        is_counterexample=True,
        error_type=confirmed_type,
        messages=[
            Message(role="user",      content=base["question"]),
            Message(role="assistant", content=mutated_answer),
        ],
        metadata={
            "original_answer": base["answer"],
            "error_injected":  confirmed_type,
        },
    )


def main():
    parser = argparse.ArgumentParser(
        description="Génération de contre-exemples EBIOS RM"
    )
    parser.add_argument("--count", type=int, default=200,
                        help="Nombre total de contre-exemples à générer")
    parser.add_argument("--error-type",
                        choices=list(MUTATION_FUNCTIONS.keys()) + ["all"],
                        default="all")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(args.seed)

    error_types = (
        list(MUTATION_FUNCTIONS.keys())
        if args.error_type == "all"
        else [args.error_type]
    )

    # Répartition équilibrée entre types d'erreur
    per_type = max(1, args.count // len(error_types))
    examples: list[CorpusExample] = []

    for error_type in error_types:
        for i in range(per_type):
            base = BASE_EXAMPLES[i % len(BASE_EXAMPLES)]
            ex = generate_counterexample(base, error_type)
            examples.append(ex)
            print(f"  [{error_type}] {ex.id} ✓")

    # Sauvegarde
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")

    print(f"\n{len(examples)} contre-exemples → {OUTPUT_PATH}")

    # Statistiques par type
    from collections import Counter
    counts = Counter(ex.error_type for ex in examples)
    for etype, n in sorted(counts.items()):
        print(f"  {etype:25s} : {n}")


if __name__ == "__main__":
    main()
