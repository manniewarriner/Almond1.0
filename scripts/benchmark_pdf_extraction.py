"""Compare uncached local extractors; prints aggregate metrics, never document text.

Run from the repo with: python scripts/benchmark_pdf_extraction.py <public-or-synthetic.pdf>
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from time import perf_counter

from app.documents.content_extract import extract_document


def benchmark(path: Path) -> None:
    results = {}
    tokens = {}
    numbers = {}
    for backend in ("pdfium", "pypdf"):
        start = perf_counter()
        content = extract_document(path, use_cache=False, pdf_backend=backend)
        elapsed = perf_counter() - start
        text = "\n".join(block.text or "" for block in content.blocks)
        tokens[backend] = Counter(re.findall(r"\w+", text.casefold()))
        numbers[backend] = Counter(re.findall(r"\b\d+(?:[.,]\d+)*\b", text))
        results[backend] = {"seconds": round(elapsed, 3), "characters": len(text)}
        print(json.dumps({backend: results[backend]}), flush=True)
    for name, counts in (("tokens", tokens), ("numbers", numbers)):
        overlap = sum((counts["pdfium"] & counts["pypdf"]).values())
        denominator = sum(counts["pypdf"].values())
        results[f"{name}_overlap_vs_pypdf"] = round(overlap / max(1, denominator), 4)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    benchmark(parser.parse_args().source)
