"""
05_format_chatml.py — Conversion du corpus filtré en format ChatML pour Unsloth/QLoRA.

Entrée  : corpus/processed/filtered.jsonl
Sortie  : corpus/datasets/train_chatml.jsonl
          corpus/datasets/eval_chatml.jsonl   (subset pré-split pour vérification)

Le format ChatML est le format natif de Mistral Instruct v0.3 :
  <|im_start|>system\n...\n<|im_end|>
  <|im_start|>user\n...\n<|im_end|>
  <|im_start|>assistant\n...\n<|im_end|>

Seuls les tokens assistant sont backpropagés (train_on_responses_only=True dans Unsloth).

Usage :
  python 05_format_chatml.py
  python 05_format_chatml.py --include-counterexamples
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from schema import SYSTEM_PROMPT, CorpusExample

ROOT         = Path(__file__).resolve().parents[1]
FILTERED     = ROOT / "processed" / "filtered.jsonl"
DATASETS_DIR = ROOT / "datasets"
DATASETS_DIR.mkdir(parents=True, exist_ok=True)

CHATML_TURN = "<|im_start|>{role}\n{content}\n<|im_end|>"
EOS_TOKEN   = "<|im_end|>"


def to_chatml_text(example: CorpusExample,
                   include_counterexamples: bool = False) -> str | None:
    """
    Convertit un CorpusExample en texte ChatML complet.
    Retourne None si l'exemple doit être ignoré.
    """
    if example.is_counterexample and not include_counterexamples:
        return None

    turns = [
        CHATML_TURN.format(role="system", content=SYSTEM_PROMPT),
    ]
    for msg in example.messages:
        turns.append(CHATML_TURN.format(role=msg.role, content=msg.content))

    return "\n".join(turns)


def main():
    parser = argparse.ArgumentParser(description="Format ChatML pour fine-tuning")
    parser.add_argument("--include-counterexamples", action="store_true",
                        help="Inclure les contre-exemples (pour DPO)")
    args = parser.parse_args()

    if not FILTERED.exists():
        sys.exit(f"Fichier introuvable : {FILTERED}\nLancer 04_quality_filter.py d'abord.")

    records: list[dict] = []
    skipped = 0

    with open(FILTERED, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            ex = CorpusExample.from_dict(d)
            text = to_chatml_text(ex, args.include_counterexamples)
            if text is None:
                skipped += 1
                continue
            records.append({
                "text": text,
                "id":      ex.id,
                "atelier": ex.atelier,
                "secteur": ex.secteur,
                "source":  ex.source,
                "is_counterexample": ex.is_counterexample,
            })

    out_path = DATASETS_DIR / "train_chatml.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"Format ChatML appliqué :")
    print(f"  {len(records)} exemples → {out_path}")
    print(f"  {skipped} exemples ignorés (contre-exemples exclus)")

    # Aperçu du premier exemple
    if records:
        print(f"\nAperçu (premier exemple — {records[0]['id']}) :")
        preview = records[0]["text"][:400]
        print(preview + "...")


if __name__ == "__main__":
    main()
