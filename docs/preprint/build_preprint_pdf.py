from __future__ import annotations

import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
MAIN_DRAFT = BASE_DIR / "preprint-draft.md"
COMBINED_DRAFT = BASE_DIR / "preprint-full-draft.md"
PDF_OUT = BASE_DIR / "preprint-full-draft.pdf"

APPENDICES = [
    ("# Appendix A: Claim-To-Evidence Matrix", BASE_DIR / "claim-evidence-matrix.md"),
    ("# Appendix B: ClaimWright Review Record", BASE_DIR / "claimwright-review.md"),
    ("# Appendix C: Memory-Layer Bibliography Notes", BASE_DIR / "memory-layer-bibliography.md"),
]


def strip_yaml_front_matter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n+", "", text, flags=re.DOTALL)


def demote_headings(text: str) -> str:
    lines: list[str] = []
    for line in text.splitlines():
        if line.startswith("#"):
            lines.append("#" + line)
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def build_combined_markdown() -> None:
    parts = [MAIN_DRAFT.read_text(encoding="utf-8").strip()]
    for heading, path in APPENDICES:
        appendix = strip_yaml_front_matter(path.read_text(encoding="utf-8"))
        parts.append(f"{heading}\n\n{demote_headings(appendix)}")
    COMBINED_DRAFT.write_text("\n\n\\newpage\n\n".join(parts) + "\n", encoding="utf-8")


def build_pdf() -> None:
    subprocess.run(
        [
            "pandoc",
            str(COMBINED_DRAFT.name),
            "-s",
            "--pdf-engine=xelatex",
            "--metadata",
            "title=Memory Layers Should Be Governed",
            "--metadata",
            "author=welsberr",
            "--metadata",
            "date=2026-07-26",
            "-o",
            str(PDF_OUT.name),
        ],
        cwd=BASE_DIR,
        check=True,
    )


def main() -> None:
    build_combined_markdown()
    build_pdf()
    print(PDF_OUT)


if __name__ == "__main__":
    main()
