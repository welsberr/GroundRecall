from __future__ import annotations

import re
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
PREPRINT_STEM = "2026-elsberry-governed-memory-layer-principles-r02"
MAIN_DRAFT = BASE_DIR / f"{PREPRINT_STEM}-source.md"
COMBINED_DRAFT = BASE_DIR / f"{PREPRINT_STEM}.md"
HTML_OUT = BASE_DIR / f"{PREPRINT_STEM}.html"
PDF_OUT = BASE_DIR / f"{PREPRINT_STEM}.pdf"

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


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return False
    cells = split_table_row(stripped)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def table_to_pdf_list(table_lines: list[str]) -> list[str]:
    if len(table_lines) < 2 or not is_table_separator(table_lines[1]):
        return table_lines
    headers = split_table_row(table_lines[0])
    rows = [split_table_row(line) for line in table_lines[2:] if line.strip()]
    rendered: list[str] = []
    for row in rows:
        padded = row + [""] * max(0, len(headers) - len(row))
        if not padded:
            continue
        title = padded[0].strip() or "Item"
        if len(headers) == 2:
            value = padded[1].strip() if len(padded) > 1 else ""
            rendered.append(f"- **{title}:** {value}")
            continue
        rendered.append(f"- **{title}**")
        for header, value in zip(headers[1:], padded[1:]):
            if value.strip():
                rendered.append(f"  - **{header.strip()}:** {value.strip()}")
    return rendered or table_lines


def convert_tables_for_pdf(text: str) -> str:
    lines = text.splitlines()
    converted: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.strip().startswith("|") and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].strip().startswith("|"):
                table_lines.append(lines[index])
                index += 1
            if converted and converted[-1].strip():
                converted.append("")
            converted.extend(table_to_pdf_list(table_lines))
            converted.append("")
            continue
        converted.append(line)
        index += 1
    return "\n".join(converted).strip()


def build_combined_markdown() -> None:
    parts = [convert_tables_for_pdf(MAIN_DRAFT.read_text(encoding="utf-8")).strip()]
    for heading, path in APPENDICES:
        appendix = strip_yaml_front_matter(path.read_text(encoding="utf-8"))
        appendix = convert_tables_for_pdf(demote_headings(appendix))
        parts.append(f"{heading}\n\n{appendix}")
    COMBINED_DRAFT.write_text("\n\n\\newpage\n\n".join(parts) + "\n", encoding="utf-8")


def build_pdf() -> None:
    subprocess.run(
        [
            "pandoc",
            str(COMBINED_DRAFT.name),
            "-s",
            "--pdf-engine=xelatex",
            "-o",
            str(PDF_OUT.name),
        ],
        cwd=BASE_DIR,
        check=True,
    )


def build_html() -> None:
    subprocess.run(
        [
            "pandoc",
            str(COMBINED_DRAFT.name),
            "-s",
            "-o",
            str(HTML_OUT.name),
        ],
        cwd=BASE_DIR,
        check=True,
    )


def main() -> None:
    build_combined_markdown()
    build_html()
    build_pdf()
    print(PDF_OUT)


if __name__ == "__main__":
    main()
