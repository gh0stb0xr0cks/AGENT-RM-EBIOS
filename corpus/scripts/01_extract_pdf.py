"""
01_extract_pdf.py — Extraction de texte depuis les sources documentaires officielles.

Sources attendues dans corpus/raw/ :
  - anssi/   : guides EBIOS RM, référentiel de qualification, fiches pratiques
  - mitre/   : ATT&CK Enterprise (PDF ou JSON)

Sortie : corpus/raw/anssi/*.txt  et  corpus/raw/mitre/*.txt
         + corpus/raw/anssi/index.jsonl  (métadonnées par chunk)

Usage :
  python 01_extract_pdf.py --source anssi
  python 01_extract_pdf.py --source mitre
  python 01_extract_pdf.py --source all
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    sys.exit("pip install pdfplumber")

# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw"
CHUNK_SIZE = 800        # tokens approximatifs (~4 chars/token → 3 200 chars)
CHUNK_OVERLAP = 80      # chevauchement pour ne pas couper les concepts


# ---------------------------------------------------------------------------
def extract_pdf(pdf_path: Path) -> str:
    """Extrait le texte brut d'un PDF avec pdfplumber."""
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
    return "\n\n".join(pages)


def clean_text(text: str) -> str:
    """Nettoyage post-extraction : sauts de ligne multiples, espaces parasites."""
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\f', '\n\n', text)        # form feeds
    text = text.strip()
    return text


def chunk_text(text: str, doc_id: str, source: str,
               chunk_size: int = CHUNK_SIZE,
               overlap: int = CHUNK_OVERLAP) -> list[dict]:
    """
    Découpe le texte en chunks de taille fixe avec chevauchement.
    Respecte les frontières de paragraphes autant que possible.
    """
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk: list[str] = []
    current_len = 0
    chunk_idx = 0

    for para in paragraphs:
        para_len = len(para) // 4  # approximation tokens
        if current_len + para_len > chunk_size and current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunks.append({
                "id":       f"{doc_id}_chunk_{chunk_idx:04d}",
                "doc_id":   doc_id,
                "source":   source,
                "chunk_idx": chunk_idx,
                "text":     chunk_text,
                "tokens_approx": len(chunk_text) // 4,
            })
            chunk_idx += 1
            # Chevauchement : on garde les N derniers paragraphes
            overlap_chars = 0
            keep = []
            for p in reversed(current_chunk):
                overlap_chars += len(p) // 4
                keep.insert(0, p)
                if overlap_chars >= overlap:
                    break
            current_chunk = keep
            current_len = sum(len(p) // 4 for p in current_chunk)

        current_chunk.append(para)
        current_len += para_len

    # Dernier chunk
    if current_chunk:
        chunk_text = '\n\n'.join(current_chunk)
        chunks.append({
            "id":       f"{doc_id}_chunk_{chunk_idx:04d}",
            "doc_id":   doc_id,
            "source":   source,
            "chunk_idx": chunk_idx,
            "text":     chunk_text,
            "tokens_approx": len(chunk_text) // 4,
        })

    return chunks


def process_directory(source_dir: Path, source_label: str) -> list[dict]:
    """Traite tous les PDFs d'un répertoire source."""
    all_chunks: list[dict] = []
    pdf_files = sorted(source_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"  [WARN] Aucun PDF trouvé dans {source_dir}")
        return []

    for pdf_path in pdf_files:
        doc_id = pdf_path.stem.lower().replace(" ", "_")
        print(f"  Extraction : {pdf_path.name}")

        try:
            raw_text = extract_pdf(pdf_path)
            cleaned = clean_text(raw_text)

            # Sauvegarde texte brut nettoyé
            txt_out = pdf_path.parent / f"{doc_id}.txt"
            txt_out.write_text(cleaned, encoding="utf-8")

            # Chunking
            chunks = chunk_text(cleaned, doc_id=doc_id, source=source_label)
            all_chunks.extend(chunks)
            print(f"    → {len(chunks)} chunks extraits")

        except Exception as e:
            print(f"  [ERREUR] {pdf_path.name} : {e}")

    return all_chunks


def write_index(chunks: list[dict], output_path: Path) -> None:
    """Écrit l'index JSONL des chunks."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    print(f"\n  Index écrit : {output_path} ({len(chunks)} chunks total)")


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Extraction PDF corpus EBIOS RM")
    parser.add_argument("--source", choices=["anssi", "mitre", "all"],
                        default="all", help="Source à traiter")
    args = parser.parse_args()

    sources_to_process = []
    if args.source in ("anssi", "all"):
        sources_to_process.append(("anssi", RAW_DIR / "anssi"))
    if args.source in ("mitre", "all"):
        sources_to_process.append(("mitre", RAW_DIR / "mitre"))

    all_chunks: list[dict] = []
    for label, directory in sources_to_process:
        print(f"\n[{label.upper()}] Traitement de {directory}")
        if not directory.exists():
            print(f"  [WARN] Répertoire inexistant : {directory}")
            continue
        chunks = process_directory(directory, source_label=label)
        all_chunks.extend(chunks)

    if all_chunks:
        write_index(all_chunks, RAW_DIR / "index.jsonl")
        total_tokens = sum(c["tokens_approx"] for c in all_chunks)
        print(f"\nRécapitulatif : {len(all_chunks)} chunks, "
              f"~{total_tokens:,} tokens")
    else:
        print("\nAucun chunk produit.")


if __name__ == "__main__":
    main()
