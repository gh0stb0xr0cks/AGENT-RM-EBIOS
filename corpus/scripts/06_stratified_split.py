"""
06_stratified_split.py — Découpage stratifié du corpus en train / eval / test.

Stratification sur (atelier × secteur) pour garantir la couverture de toutes
les combinaisons dans chaque split.

  Train : 80%
  Eval  : 10%  (monitoring pendant fine-tuning)
  Test  : 10%  (évaluation finale, jamais vu pendant l'entraînement)

Produit :
  corpus/datasets/train.jsonl
  corpus/datasets/eval.jsonl
  corpus/datasets/test.jsonl
  corpus/datasets/split_stats.json

Usage :
  python 06_stratified_split.py
  python 06_stratified_split.py --train 0.8 --eval 0.1 --test 0.1 --seed 42
"""
from __future__ import annotations
import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path

ROOT         = Path(__file__).resolve().parents[1]
CHATML_FILE  = ROOT / "datasets" / "train_chatml.jsonl"
DATASETS_DIR = ROOT / "datasets"


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def write_jsonl(records: list[dict], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def stratified_split(
    records: list[dict],
    train_ratio: float,
    eval_ratio: float,
    test_ratio: float,
    seed: int,
) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Répartit en conservant la distribution (atelier × secteur) dans chaque split.
    """
    assert abs(train_ratio + eval_ratio + test_ratio - 1.0) < 1e-6

    # Groupement par strate
    strata: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        key = f"{r.get('atelier','?')}_{r.get('secteur','?')}"
        strata[key].append(r)

    rng = random.Random(seed)
    train, eval_, test = [], [], []

    for key, group in strata.items():
        rng.shuffle(group)
        n = len(group)
        n_test  = max(1, math.floor(n * test_ratio))
        n_eval  = max(1, math.floor(n * eval_ratio))
        n_train = n - n_test - n_eval

        # Garantit au moins 1 exemple par split même pour les petits groupes
        if n < 3:
            train.extend(group)
            continue

        train.extend(group[:n_train])
        eval_.extend(group[n_train:n_train + n_eval])
        test.extend(group[n_train + n_eval:])

    # Shuffle final
    rng.shuffle(train)
    rng.shuffle(eval_)
    rng.shuffle(test)

    return train, eval_, test


def main():
    parser = argparse.ArgumentParser(
        description="Split stratifié du corpus EBIOS RM"
    )
    parser.add_argument("--train", type=float, default=0.80)
    parser.add_argument("--eval",  type=float, default=0.10)
    parser.add_argument("--test",  type=float, default=0.10)
    parser.add_argument("--seed",  type=int,   default=42)
    args = parser.parse_args()

    assert abs(args.train + args.eval + args.test - 1.0) < 1e-6, \
        "train + eval + test doit égaler 1.0"

    if not CHATML_FILE.exists():
        sys.exit(f"Fichier introuvable : {CHATML_FILE}\nLancer 05_format_chatml.py d'abord.")

    print(f"Chargement de {CHATML_FILE}...")
    records = load_jsonl(CHATML_FILE)
    print(f"  {len(records)} exemples chargés")

    train, eval_, test = stratified_split(
        records,
        train_ratio=args.train,
        eval_ratio=args.eval,
        test_ratio=args.test,
        seed=args.seed,
    )

    write_jsonl(train, DATASETS_DIR / "train.jsonl")
    write_jsonl(eval_,  DATASETS_DIR / "eval.jsonl")
    write_jsonl(test,   DATASETS_DIR / "test.jsonl")

    # Statistiques par atelier
    def atelier_dist(lst: list[dict]) -> dict:
        d: dict[str, int] = defaultdict(int)
        for r in lst:
            d[r.get("atelier", "?")] += 1
        return dict(sorted(d.items()))

    stats = {
        "total": len(records),
        "train": {"count": len(train), "by_atelier": atelier_dist(train)},
        "eval":  {"count": len(eval_),  "by_atelier": atelier_dist(eval_)},
        "test":  {"count": len(test),   "by_atelier": atelier_dist(test)},
        "seed":  args.seed,
    }

    stats_path = DATASETS_DIR / "split_stats.json"
    with open(stats_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print(f"\nSplit stratifié (seed={args.seed}) :")
    print(f"  Train : {len(train):>5} ({args.train*100:.0f}%)  {atelier_dist(train)}")
    print(f"  Eval  : {len(eval_):>5} ({args.eval*100:.0f}%)   {atelier_dist(eval_)}")
    print(f"  Test  : {len(test):>5} ({args.test*100:.0f}%)   {atelier_dist(test)}")
    print(f"\nStats → {stats_path}")


if __name__ == "__main__":
    main()
