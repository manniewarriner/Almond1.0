"""Time an entire local conversion of a public or synthetic PDF, with stage progress."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

from app.documents.content_extract import clear_extraction_cache
from app.pdf.service import create_branded_pdf


def benchmark(source: Path) -> None:
    output_dir = Path(mkdtemp(prefix="almond-pdf-benchmark-"))
    clear_extraction_cache()
    start = perf_counter()

    def progress(message: str) -> None:
        print(f"{perf_counter() - start:.2f}s: {message}", flush=True)

    result = create_branded_pdf(source, output_dir, fast=True, progress=progress)
    print(
        json.dumps(
            {
                "seconds": round(perf_counter() - start, 3),
                "pages": result.pages,
                "words": result.word_count,
                "output": result.output_path,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    benchmark(parser.parse_args().source)
