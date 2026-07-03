from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


def load_startup_profile(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    profile_path = Path(path)
    payload = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Startup profile must be a mapping: {profile_path}")
    payload.setdefault("profile_path", str(profile_path))
    return payload


def profile_concept_refs(profile: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("curated_concepts", "concepts"):
        value = profile.get(key, [])
        if isinstance(value, list):
            refs.extend(str(item).strip() for item in value if str(item).strip())
    return refs


def merge_concept_refs(explicit_refs: list[str] | None, profile: dict[str, Any]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for ref in [*(explicit_refs or []), *profile_concept_refs(profile)]:
        normalized = " ".join(str(ref).split())
        if normalized and normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
    return merged


def recent_source_notes(store_dir: str | Path, limit: int = 8) -> list[dict[str, str]]:
    if limit <= 0:
        return []
    source_notes_dir = Path(store_dir).parent / "source-notes"
    if not source_notes_dir.exists():
        return []
    notes = sorted(source_notes_dir.glob("*.md"), key=lambda item: item.stat().st_mtime, reverse=True)
    return [
        {
            "title": note.stem,
            "path": str(note),
            "mtime": datetime.fromtimestamp(note.stat().st_mtime, timezone.utc).isoformat(),
        }
        for note in notes[:limit]
    ]


def build_startup_context(
    *,
    store_dir: str | Path,
    assistant: str,
    profile: dict[str, Any],
    requested_concepts: list[str],
    query_bundles: list[dict[str, Any]],
    unresolved_concepts: list[str],
) -> dict[str, Any]:
    recent_note_count = int(profile.get("recent_note_count", 8) or 0)
    return {
        "assistant": assistant,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile_path": str(profile.get("profile_path", "")),
        "host": profile.get("host", {}),
        "store_dir": str(store_dir),
        "canonical_export_dir": str(profile.get("canonical_export_dir", "")),
        "active_repos": list(profile.get("active_repos", []) or []),
        "standing_premises": list(profile.get("standing_premises", []) or []),
        "startup_reminders": list(profile.get("startup_reminders", []) or []),
        "requested_concepts": requested_concepts,
        "resolved_concepts": _resolved_concepts(requested_concepts, query_bundles, unresolved_concepts),
        "unresolved_concepts": unresolved_concepts,
        "recent_source_notes": recent_source_notes(store_dir, limit=recent_note_count),
    }


def _resolved_concepts(
    requested_concepts: list[str],
    query_bundles: list[dict[str, Any]],
    unresolved_concepts: list[str],
) -> list[dict[str, Any]]:
    unresolved = set(unresolved_concepts)
    resolved: list[dict[str, Any]] = []
    bundle_index = 0
    for requested_ref in requested_concepts:
        if requested_ref in unresolved:
            continue
        if bundle_index >= len(query_bundles):
            break
        bundle = query_bundles[bundle_index]
        bundle_index += 1
        concept = bundle.get("concept", {}) if isinstance(bundle.get("concept"), dict) else {}
        title = str(concept.get("title", "") or concept.get("concept_id", "") or requested_ref)
        resolved.append(
            {
                "requested_ref": requested_ref,
                "concept_id": concept.get("concept_id", ""),
                "title": title,
                "claim_count": len(bundle.get("relevant_claims", []) or []),
                "relation_count": len(bundle.get("relations", []) or []),
            }
        )
    return resolved


def render_startup_markdown(startup_context: dict[str, Any]) -> str:
    lines = [
        "# GroundRecall Startup Brief",
        "",
        f"- Assistant: `{startup_context.get('assistant', '')}`",
        f"- Store: `{startup_context.get('store_dir', '')}`",
    ]
    if startup_context.get("canonical_export_dir"):
        lines.append(f"- Canonical export: `{startup_context['canonical_export_dir']}`")
    host = startup_context.get("host") if isinstance(startup_context.get("host"), dict) else {}
    if host:
        host_bits = ", ".join(f"{key}={value}" for key, value in host.items() if value)
        if host_bits:
            lines.append(f"- Host: {host_bits}")

    lines.extend(["", "## Active Repositories"])
    repos = startup_context.get("active_repos", []) or []
    if repos:
        for repo in repos:
            if isinstance(repo, dict):
                label = repo.get("name") or repo.get("path") or repo.get("url") or "repo"
                detail = " | ".join(str(repo.get(key, "")) for key in ("path", "url", "branch") if repo.get(key))
                lines.append(f"- {label}: {detail}" if detail else f"- {label}")
            else:
                lines.append(f"- {repo}")
    else:
        lines.append("- No active repositories listed in the startup profile.")

    lines.extend(["", "## Standing Premises"])
    premises = startup_context.get("standing_premises", []) or []
    lines.extend(f"- {item}" for item in premises) if premises else lines.append("- No standing premises listed.")

    lines.extend(["", "## Curated Concepts"])
    resolved = startup_context.get("resolved_concepts", []) or []
    if resolved:
        for item in resolved:
            label = item.get("title") or item.get("requested_ref") or item.get("concept_id")
            lines.append(
                f"- {label}: "
                f"{item.get('claim_count', 0)} claims, {item.get('relation_count', 0)} relations"
            )
    else:
        lines.append("- No curated concepts resolved.")
    unresolved = startup_context.get("unresolved_concepts", []) or []
    if unresolved:
        lines.append("")
        lines.append("Unresolved concept refs:")
        lines.extend(f"- `{item}`" for item in unresolved)

    lines.extend(["", "## Recent Source Notes"])
    notes = startup_context.get("recent_source_notes", []) or []
    if notes:
        lines.extend(f"- {item.get('title', '')}: `{item.get('path', '')}`" for item in notes)
    else:
        lines.append("- No recent source notes found.")

    lines.extend(["", "## Startup Reminders"])
    reminders = startup_context.get("startup_reminders", []) or []
    if reminders:
        lines.extend(f"- {item}" for item in reminders)
    else:
        lines.append("- Query GroundRecall before broad filesystem searches or planning changes.")
    lines.append("")
    return "\n".join(lines)
