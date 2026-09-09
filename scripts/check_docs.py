#!/usr/bin/env python3
"""Reconcile every project Markdown document and capability record."""
import re
import os
from pathlib import Path
from urllib.parse import unquote

from atlas.domain.contracts import TOOL_VERSION, stage_contracts

REQUIRED = {"README.md", "design.md", "minimal-test.md", "test-method.md", "test-output.txt", "output-explanation.md", "test-log.md"}
CURRENT_DOCS = ("SKILL.md", "README.md", "TEST_REPORT.md", "DEVELOPMENT_PLAN.md", "references/capabilities.md")


def markdown_links(path):
    text = path.read_text(encoding="utf-8")
    targets=[]
    for target in re.findall(r"\[[^]]+\]\(([^)]+)\)",text):
        target=unquote(target.strip().strip('<>')).split("#",1)[0]
        if target and not re.match(r"(?:[a-z]+:)?//|mailto:",target):targets.append(target)
    return targets


def markdown_documents(root):
    documents=[]
    for directory,subdirectories,files in os.walk(root):
        subdirectories[:]=[name for name in subdirectories if name not in (".git","runtime","node_modules")]
        documents.extend(Path(directory)/name for name in files if name.endswith(".md"))
    return sorted(documents)


def check(root):
    errors = []
    skill = root / "SKILL.md"
    documents=markdown_documents(root)
    for source in documents:
        for target in markdown_links(source):
            if target and not (source.parent / target).resolve().exists():
                errors.append(f"broken link: {source.relative_to(root)} -> {target}")
    skill_text = skill.read_text(encoding="utf-8")
    if TOOL_VERSION not in skill_text:
        errors.append(f"SKILL.md must state current tool version {TOOL_VERSION}")
    for current in CURRENT_DOCS:
        text=(root/current).read_text(encoding="utf-8")
        if TOOL_VERSION.rsplit('.',1)[0] not in text:
            errors.append(f"{current} must state current minor version {TOOL_VERSION.rsplit('.',1)[0]}")
    feature_root = root / "do_func";directories=sorted(path for path in feature_root.iterdir() if path.is_dir())
    expected=list(range(1,len(directories)+1));actual=[];catalog=(feature_root/"README.md").read_text(encoding="utf-8")
    for directory in directories:
        match=re.match(r"(\d{2})-[a-z0-9-]+$",directory.name)
        if not match:errors.append(f"capability folder needs NN-name format: {directory.name}")
        else:actual.append(int(match.group(1)))
        if f"({directory.name}/README.md)" not in catalog:errors.append(f"capability catalog missing {directory.name}")
        missing = REQUIRED - {path.name for path in directory.iterdir() if path.is_file()}
        if missing:
            errors.append(f"{directory.name}: missing {', '.join(sorted(missing))}")
    if actual!=expected:errors.append(f"capability sequence must be contiguous: {actual}")
    workflow = (root / "references" / "workflow-checkpoints.md").read_text(encoding="utf-8")
    for stage in stage_contracts():
        if f"`{stage.name}`" not in workflow or f"`{stage.checkpoint}`" not in workflow:
            errors.append(f"workflow contract missing {stage.name}/{stage.checkpoint}")
        for product in stage.outputs:
            if f"`{product}`" not in workflow:errors.append(f"workflow output missing {stage.name}/{product}")
    return errors


if __name__ == "__main__":
    repository = Path(__file__).resolve().parents[1]
    failures = check(repository)
    if failures:
        raise SystemExit("\n".join(failures))
    print(f"documentation reconciliation: PASS ({len(markdown_documents(repository))} Markdown files, complete local-link coverage)")
