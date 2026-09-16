"""Synthetic, local-only model-to-PDF smoke test. Starts/reuses the shared model server."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import mkdtemp
from time import perf_counter

from pypdf import PdfReader

from almond_ai.config import DeveloperConfig, ModelSettings
from almond_ai.core import AlmondCore


def main() -> None:
    directory = Path(mkdtemp(prefix="almond-document-ai-"))
    source = directory / "synthetic.txt"
    source.write_text(
        "Quarterly Overview\n\nSynthetic balance: GBP 1,234.56. Change: -12.5%.\n\n"
        "Next Steps\n\n- Review the figures\n- Confirm availability\n\n"
        "The proposed meeting is not confirmed.",
        encoding="utf-8",
    )
    core = AlmondCore(DeveloperConfig(model=ModelSettings(provider="llama_cpp")))
    core.base_config.outputs_dir = directory / "outputs"
    core.base_config.audit_db_path = directory / "audit.db"
    start = perf_counter()

    def progress(message: str) -> None:
        print(f"{perf_counter() - start:.2f}s: {message}", flush=True)

    result = core.create_pdf(str(source), ai_format=True, fast=True, progress=progress)
    text = " ".join(page.extract_text() for page in PdfReader(result.output_path).pages)
    for expected in ("1,234.56", "-12.5%", "not confirmed", "Review the figures"):
        assert expected in text
    assert result.formatting_method == "ai_structure"
    print(
        json.dumps(
            {
                "seconds": round(perf_counter() - start, 3),
                "method": result.formatting_method,
                "pages": result.pages,
                "output": result.output_path,
            }
        ),
        flush=True,
    )
    # Keep the shared server available to the app; do not stop another bot's runtime.


if __name__ == "__main__":
    main()
