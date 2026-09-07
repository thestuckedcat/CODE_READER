#!/usr/bin/env python3
"""Reject stale Skill links, version drift, and incomplete capability records."""
import re
from pathlib import Path

from atlas.domain.contracts import TOOL_VERSION, stage_contracts

REQUIRED = {"design.md", "minimal-test.md", "test-method.md", "test-output.txt", "output-explanation.md"}


def markdown_links(path):
    text = path.read_text(encoding="utf-8")
    return [target.split("#", 1)[0] for target in re.findall(r"\[[^]]+\]\(([^)]+)\)", text) if not re.match(r"[a-z]+://", target)]


def check(root):
    errors = []
    skill = root / "SKILL.md"
    for source in [skill, root / "README.md"]:
        for target in markdown_links(source):
            if target and not (source.parent / target).resolve().exists():
                errors.append(f"broken link: {source.relative_to(root)} -> {target}")
    skill_text = skill.read_text(encoding="utf-8")
    if TOOL_VERSION not in skill_text:
        errors.append(f"SKILL.md must state current tool version {TOOL_VERSION}")
    feature_root = root / "do_func"
    for directory in sorted(path for path in feature_root.iterdir() if path.is_dir()):
        missing = REQUIRED - {path.name for path in directory.iterdir() if path.is_file()}
        if missing:
            errors.append(f"{directory.name}: missing {', '.join(sorted(missing))}")
    workflow = (root / "references" / "workflow-checkpoints.md").read_text(encoding="utf-8")
    for stage in stage_contracts():
        if f"`{stage.name}`" not in workflow or f"`{stage.checkpoint}`" not in workflow:
            errors.append(f"workflow contract missing {stage.name}/{stage.checkpoint}")
    return errors


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    failures = check(repository)
    if failures:
        raise SystemExit("\n".join(failures))
    print("documentation reconciliation: PASS")
