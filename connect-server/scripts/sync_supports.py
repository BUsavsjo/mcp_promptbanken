"""Bygger Connects stödkatalog från Promptbankens auktoritativa skillkällor.

Källan är `agent-skills/` i repot `promptbanken`. Connect redigerar aldrig
metoderna själv: den här filen kopierar dem oförändrade och skriver ett
manifest med version, källcommit och kontrollsummor. Kör så här:

    git -C <promptbanken> archive <ref> agent-skills | tar -x -C <tmp>
    python scripts/sync_supports.py --source <tmp>/agent-skills --commit <sha>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

SUPPORT_IDS = (
    "motessekreteraren",
    "utredaren",
    "processledaren",
    "forbattringsledaren",
    "forandringsledaren",
    "verksamhetsanalytikern",
    "workshopledaren",
    "produktutvecklaren",
    "superplan",
)

TEXT_SUFFIXES = {".md", ".mjs", ".js", ".py", ".txt", ".json", ".csv"}
SKIPPED_DIRS = {"agents"}

OPEN_TOOL_NAMES = ("get_template", "search_templates", "list_package_prompts", "list_packages", "get_package")
OTHER_SKILL_REFERENCES = ("processkartan",)

TARGET = Path(__file__).resolve().parents[1] / "connect_service" / "supports"


def _frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    if not match:
        raise ValueError("SKILL.md saknar frontmatter.")
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        stripped = line.strip()
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        fields[key.strip()] = value.strip().strip('"')
    return fields, text[match.end():]


def _display_name(skill_dir: Path, body: str) -> str:
    agents = skill_dir / "agents" / "openai.yaml"
    if agents.exists():
        found = re.search(r'display_name:\s*"([^"]+)"', agents.read_text(encoding="utf-8"))
        if found:
            return found.group(1)
    heading = re.search(r"^# (.+)$", body, re.M)
    return heading.group(1).strip() if heading else skill_dir.name


def _split_description(description: str) -> tuple[str, str]:
    marker = re.search(r"\bAnvänd inte\b", description)
    if not marker:
        return description.strip(), ""
    return description[: marker.start()].strip(), description[marker.start():].strip()


def _requirements(skill_dir: Path, files: list[str]) -> dict[str, object]:
    corpus = "\n".join((skill_dir / name).read_text(encoding="utf-8") for name in files)
    return {
        "open_catalog_tools": sorted(name for name in OPEN_TOOL_NAMES if f"`{name}`" in corpus),
        "code_execution": any(name.startswith("scripts/") for name in files),
        "other_skills": sorted(name for name in OTHER_SKILL_REFERENCES if name in corpus.casefold() and name != skill_dir.name),
    }


def build(source: Path, commit: str) -> dict[str, object]:
    if TARGET.exists():
        shutil.rmtree(TARGET)
    TARGET.mkdir(parents=True)
    supports = []
    for support_id in SUPPORT_IDS:
        skill_dir = source / support_id
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise SystemExit(f"Blockerare: källan för {support_id} saknas i {source}.")
        fields, body = _frontmatter(skill_md.read_text(encoding="utf-8"))
        files = sorted(
            path.relative_to(skill_dir).as_posix()
            for path in skill_dir.rglob("*")
            if path.is_file()
            and path.suffix in TEXT_SUFFIXES
            and path.relative_to(skill_dir).parts[0] not in SKIPPED_DIRS
        )
        entries = []
        for name in files:
            data = (skill_dir / name).read_bytes()
            destination = TARGET / support_id / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
            entries.append({"path": name, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)})
        use_when, not_when = _split_description(fields.get("description", ""))
        supports.append(
            {
                "id": support_id,
                "name": _display_name(skill_dir, body),
                "use_when": use_when,
                "not_when": not_when,
                "version": fields.get("version", "okänd"),
                "files": entries,
                "requires": _requirements(skill_dir, files),
            }
        )
    manifest = {"source": "promptbanken/agent-skills", "source_commit": commit, "supports": supports}
    (TARGET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    manifest = build(args.source, args.commit)
    print(f"{len(manifest['supports'])} stöd synkade från {args.commit}.")


if __name__ == "__main__":
    main()
