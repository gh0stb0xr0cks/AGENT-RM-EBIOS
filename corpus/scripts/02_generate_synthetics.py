"""
02_generate_synthetics.py — Génération à l'échelle des exemples Q/A synthétiques
via API Ollama (modèle local, air-gapped) ou Anthropic Claude (phase bootstrap).

Produit : corpus/raw/synthetics/a{1-5}_{secteur}.jsonl

Usage :
  # Génération locale (Ollama) — défaut, mode production air-gapped
  python 02_generate_synthetics.py --backend ollama --model mistral

  # Bootstrap via Claude API (phase initiale uniquement)
  python 02_generate_synthetics.py --backend claude --count 50

  # Cibler un atelier/secteur spécifique
  python 02_generate_synthetics.py --atelier A3 --secteur sante --count 30
"""
from __future__ import annotations
import argparse
import json
import random
import sys
import time
import uuid
from pathlib import Path

# Import du schema commun
sys.path.insert(0, str(Path(__file__).parent))
from schema import (
    SECTORS, GENERATION_TEMPLATES, GENERATION_THEMES,
    SYSTEM_PROMPT, CorpusExample, Message,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "raw" / "synthetics"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ATELIERS = ["A1", "A2", "A3", "A4", "A5"]

# Répartition cible du corpus (~6 000 exemples)
TARGET_PER_ATELIER_SECTEUR = {
    "A1": 4,    # 4 × 14 secteurs = 56 → simple, moins de variantes
    "A2": 5,
    "A3": 12,   # cœur du modèle, plus d'exemples
    "A4": 12,
    "A5": 6,
}


# ---------------------------------------------------------------------------
# Backend Ollama (production, air-gapped)
# ---------------------------------------------------------------------------

def generate_ollama(prompt: str, model: str = "mistral",
                    host: str = "http://localhost:11434") -> str:
    """Génère via Ollama en local."""
    try:
        import requests
    except ImportError:
        sys.exit("pip install requests")

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024},
    }
    resp = requests.post(f"{host}/api/chat", json=payload, timeout=120)
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Backend Claude API (bootstrap uniquement)
# ---------------------------------------------------------------------------

def generate_claude(prompt: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Génère via API Anthropic (nécessite ANTHROPIC_API_KEY)."""
    try:
        import anthropic
    except ImportError:
        sys.exit("pip install anthropic")

    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        sys.exit("ANTHROPIC_API_KEY non définie")

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Parsing de la réponse LLM → CorpusExample
# ---------------------------------------------------------------------------

def parse_response(raw: str, atelier: str, secteur: str,
                   theme: str, backend: str) -> CorpusExample:
    """
    Tente d'extraire question et réponse depuis la réponse brute.
    Format attendu du LLM :
      **Question :** ...
      **Réponse :** ...
    Fallback : question = theme, réponse = texte brut.
    """
    import re
    q_match = re.search(
        r'(?:\*{0,2}Question\s*:?\*{0,2})\s*(.+?)(?=\n\*{0,2}R[eé]ponse|\Z)',
        raw, re.DOTALL | re.IGNORECASE
    )
    a_match = re.search(
        r'(?:\*{0,2}R[eé]ponse\s*:?\*{0,2})\s*(.+)',
        raw, re.DOTALL | re.IGNORECASE
    )

    question = q_match.group(1).strip() if q_match else f"[{theme}] — {atelier} / {secteur}"
    answer   = a_match.group(1).strip() if a_match else raw.strip()

    example_id = f"qa_{secteur}_{atelier.lower()}_{uuid.uuid4().hex[:8]}"

    return CorpusExample(
        id=example_id,
        atelier=atelier,
        secteur=secteur,
        source="synthetic",
        messages=[
            Message(role="user",      content=question),
            Message(role="assistant", content=answer),
        ],
        metadata={
            "theme":       theme,
            "backend":     backend,
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
    )


# ---------------------------------------------------------------------------
# Génération principale
# ---------------------------------------------------------------------------

def generate_batch(atelier: str, secteur: str, count: int,
                   backend: str, model: str,
                   delay: float = 1.0) -> list[CorpusExample]:
    """Génère `count` exemples pour un couple (atelier, secteur)."""
    results: list[CorpusExample] = []
    themes = GENERATION_THEMES[atelier]
    template = GENERATION_TEMPLATES[atelier]

    for i in range(count):
        theme = themes[i % len(themes)]
        prompt = template.format(secteur=secteur, theme=theme)

        # Variation de prompt pour plus de diversité
        if i % 3 == 0:
            prompt += "\n\nPrésente la question du point de vue d'un RSSI débutant."
        elif i % 3 == 1:
            prompt += "\n\nPrésente la question du point de vue d'un consultant EBIOS RM confirmé."
        else:
            prompt += "\n\nPrésente la question dans un contexte d'audit de sécurité."

        try:
            if backend == "ollama":
                raw = generate_ollama(prompt, model=model)
            else:
                raw = generate_claude(prompt)

            example = parse_response(raw, atelier, secteur, theme, backend)
            results.append(example)
            print(f"    [{i+1}/{count}] {example.id} ✓")

        except Exception as e:
            print(f"    [{i+1}/{count}] ERREUR : {e}")

        if i < count - 1:
            time.sleep(delay)

    return results


def save_batch(examples: list[CorpusExample], atelier: str, secteur: str) -> Path:
    out_path = OUTPUT_DIR / f"{atelier.lower()}_{secteur}.jsonl"
    # Append si le fichier existe déjà (reprise après interruption)
    with open(out_path, "a", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Génération du corpus synthétique EBIOS RM"
    )
    parser.add_argument("--backend", choices=["ollama", "claude"],
                        default="ollama")
    parser.add_argument("--model",   default="mistral",
                        help="Modèle Ollama à utiliser")
    parser.add_argument("--atelier", choices=ATELIERS + ["all"],
                        default="all")
    parser.add_argument("--secteur", choices=SECTORS + ["all"],
                        default="all")
    parser.add_argument("--count",   type=int, default=0,
                        help="Nb exemples par couple (0 = valeur cible par défaut)")
    parser.add_argument("--delay",   type=float, default=0.5,
                        help="Délai entre requêtes (secondes)")
    parser.add_argument("--seed",    type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    ateliers = ATELIERS if args.atelier == "all" else [args.atelier]
    secteurs = SECTORS  if args.secteur == "all" else [args.secteur]

    total_generated = 0
    for atelier in ateliers:
        for secteur in secteurs:
            count = args.count or TARGET_PER_ATELIER_SECTEUR[atelier]
            print(f"\n[{atelier}] {secteur} — {count} exemples ({args.backend})")
            examples = generate_batch(
                atelier, secteur, count,
                backend=args.backend,
                model=args.model,
                delay=args.delay,
            )
            out = save_batch(examples, atelier, secteur)
            total_generated += len(examples)
            print(f"  → {len(examples)} exemples → {out}")

    print(f"\nTotal généré : {total_generated} exemples")


if __name__ == "__main__":
    main()
