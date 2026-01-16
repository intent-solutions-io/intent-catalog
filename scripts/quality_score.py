#!/usr/bin/env python3
"""
Quality Scoring Dashboard

Computes completeness scores for plugins and skills based on documentation coverage.
Outputs quality_report.json and quality_report.md.

Usage:
    python quality_score.py [--catalog PATH] [--out-json PATH] [--out-md PATH]
"""

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CATALOG_PATH = Path(__file__).parent.parent / "dist" / "catalog.json"
REPORT_JSON_PATH = Path(__file__).parent.parent / "dist" / "quality_report.json"
REPORT_MD_PATH = Path(__file__).parent.parent / "dist" / "quality_report.md"

# Documentation types to check for
DOC_TYPES = {
    "spec": {"label": "PRD/Spec", "weight": 20},
    "decision": {"label": "ADR/Decision", "weight": 15},
    "report": {"label": "AAR/Report", "weight": 10},
    "use_case": {"label": "Use Case", "weight": 15},
    "evidence": {"label": "Evidence", "weight": 5},
    "runbook": {"label": "Runbook", "weight": 20},
    "guide": {"label": "Guide", "weight": 10},
    "reference": {"label": "Reference", "weight": 5},
}


@dataclass
class EntityScore:
    """Quality score for a single entity."""
    entity_id: str
    entity_type: str
    name: str
    source_repo: str
    score: int = 0
    max_score: int = 100
    has_docs: dict = field(default_factory=dict)
    missing_docs: list = field(default_factory=list)
    linked_docs: list = field(default_factory=list)


def compute_entity_score(
    entity: dict,
    entity_type: str,
    relationships: list[dict],
    documents: dict,
) -> EntityScore:
    """Compute quality score for a single entity."""
    entity_id = entity.get(f"{entity_type}_id") or entity.get("plugin_id") or entity.get("skill_id")

    score = EntityScore(
        entity_id=entity_id,
        entity_type=entity_type,
        name=entity.get("name", entity_id),
        source_repo=entity.get("source_repo", "unknown"),
    )

    # Find linked documents
    linked_doc_ids = set()
    for rel in relationships:
        if rel.get("source_type") == entity_type and rel.get("source_id") == entity_id:
            if rel.get("target_type") == "document":
                linked_doc_ids.add(rel.get("target_id"))

    # Check which doc types are present
    for doc_id in linked_doc_ids:
        doc = documents.get(doc_id, {})
        doc_type = doc.get("doc_type", "unknown")
        if doc_type in DOC_TYPES:
            score.has_docs[doc_type] = True
            score.linked_docs.append({
                "doc_id": doc_id,
                "title": doc.get("title", doc_id),
                "doc_type": doc_type,
            })

    # Calculate score based on doc types present
    total_weight = sum(d["weight"] for d in DOC_TYPES.values())
    earned_weight = 0

    for doc_type, info in DOC_TYPES.items():
        if doc_type in score.has_docs:
            earned_weight += info["weight"]
        else:
            score.missing_docs.append(doc_type)

    # Also give points for basic metadata
    base_score = 0
    if entity.get("description"):
        base_score += 10
    if entity.get("version"):
        base_score += 5

    # Compute final score (0-100)
    doc_score = (earned_weight / total_weight) * 85 if total_weight > 0 else 0
    score.score = min(100, int(base_score + doc_score))

    return score


def generate_quality_report(catalog: dict) -> dict:
    """Generate quality report from catalog."""
    plugins = catalog.get("plugins", [])
    skills = catalog.get("skills", [])
    documents = catalog.get("documents", [])
    relationships = catalog.get("relationships", [])

    # Build document lookup
    doc_lookup = {d["doc_id"]: d for d in documents}

    # Score all entities
    plugin_scores = []
    for plugin in plugins:
        score = compute_entity_score(plugin, "plugin", relationships, doc_lookup)
        plugin_scores.append(score)

    skill_scores = []
    for skill in skills:
        score = compute_entity_score(skill, "skill", relationships, doc_lookup)
        skill_scores.append(score)

    # Sort by score (lowest first to highlight gaps)
    plugin_scores.sort(key=lambda x: x.score)
    skill_scores.sort(key=lambda x: x.score)

    # Compute aggregates
    avg_plugin_score = sum(s.score for s in plugin_scores) / len(plugin_scores) if plugin_scores else 0
    avg_skill_score = sum(s.score for s in skill_scores) / len(skill_scores) if skill_scores else 0

    # Find most common missing doc types
    missing_counts = {dt: 0 for dt in DOC_TYPES}
    for score in plugin_scores + skill_scores:
        for missing in score.missing_docs:
            if missing in missing_counts:
                missing_counts[missing] += 1

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_plugins": len(plugins),
            "total_skills": len(skills),
            "total_documents": len(documents),
            "avg_plugin_score": round(avg_plugin_score, 1),
            "avg_skill_score": round(avg_skill_score, 1),
            "plugins_below_50": len([s for s in plugin_scores if s.score < 50]),
            "skills_below_50": len([s for s in skill_scores if s.score < 50]),
        },
        "missing_doc_counts": {
            DOC_TYPES[dt]["label"]: count
            for dt, count in sorted(missing_counts.items(), key=lambda x: -x[1])
        },
        "plugins": [
            {
                "id": s.entity_id,
                "name": s.name,
                "repo": s.source_repo,
                "score": s.score,
                "has_docs": s.has_docs,
                "missing_docs": s.missing_docs,
            }
            for s in plugin_scores
        ],
        "skills": [
            {
                "id": s.entity_id,
                "name": s.name,
                "repo": s.source_repo,
                "score": s.score,
                "has_docs": s.has_docs,
                "missing_docs": s.missing_docs,
            }
            for s in skill_scores
        ],
    }


def generate_markdown_report(report: dict) -> str:
    """Generate human-readable markdown report."""
    lines = []

    lines.append("# Quality Report")
    lines.append("")
    lines.append(f"Generated: {report['timestamp']}")
    lines.append("")

    # Summary
    summary = report["summary"]
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Value |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total Plugins | {summary['total_plugins']} |")
    lines.append(f"| Total Skills | {summary['total_skills']} |")
    lines.append(f"| Total Documents | {summary['total_documents']} |")
    lines.append(f"| Avg Plugin Score | {summary['avg_plugin_score']}% |")
    lines.append(f"| Avg Skill Score | {summary['avg_skill_score']}% |")
    lines.append(f"| Plugins Below 50% | {summary['plugins_below_50']} |")
    lines.append(f"| Skills Below 50% | {summary['skills_below_50']} |")
    lines.append("")

    # Missing doc counts
    lines.append("## Documentation Gaps")
    lines.append("")
    lines.append("Most commonly missing documentation types:")
    lines.append("")
    lines.append("| Doc Type | Missing Count |")
    lines.append("|----------|---------------|")
    for doc_type, count in report["missing_doc_counts"].items():
        lines.append(f"| {doc_type} | {count} |")
    lines.append("")

    # Lowest scoring plugins
    lines.append("## Plugins Needing Attention")
    lines.append("")
    lines.append("Plugins with lowest quality scores:")
    lines.append("")
    lines.append("| Plugin | Score | Repo | Missing Docs |")
    lines.append("|--------|-------|------|--------------|")
    for plugin in report["plugins"][:20]:
        missing = ", ".join(plugin["missing_docs"][:3])
        if len(plugin["missing_docs"]) > 3:
            missing += f" (+{len(plugin['missing_docs']) - 3})"
        lines.append(f"| {plugin['name'][:40]} | {plugin['score']}% | {plugin['repo']} | {missing} |")
    lines.append("")

    # Lowest scoring skills
    lines.append("## Skills Needing Attention")
    lines.append("")
    lines.append("Skills with lowest quality scores:")
    lines.append("")
    lines.append("| Skill | Score | Repo | Missing Docs |")
    lines.append("|-------|-------|------|--------------|")
    for skill in report["skills"][:20]:
        missing = ", ".join(skill["missing_docs"][:3])
        if len(skill["missing_docs"]) > 3:
            missing += f" (+{len(skill['missing_docs']) - 3})"
        lines.append(f"| {skill['name'][:40]} | {skill['score']}% | {skill['repo']} | {missing} |")
    lines.append("")

    # Score distribution
    lines.append("## Score Distribution")
    lines.append("")

    # Plugin distribution
    plugin_dist = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for p in report["plugins"]:
        if p["score"] <= 25:
            plugin_dist["0-25"] += 1
        elif p["score"] <= 50:
            plugin_dist["26-50"] += 1
        elif p["score"] <= 75:
            plugin_dist["51-75"] += 1
        else:
            plugin_dist["76-100"] += 1

    lines.append("### Plugins")
    lines.append("")
    lines.append("| Score Range | Count |")
    lines.append("|-------------|-------|")
    for range_str, count in plugin_dist.items():
        bar = "█" * (count // 10) if count > 0 else ""
        lines.append(f"| {range_str}% | {count} {bar} |")
    lines.append("")

    # Skill distribution
    skill_dist = {"0-25": 0, "26-50": 0, "51-75": 0, "76-100": 0}
    for s in report["skills"]:
        if s["score"] <= 25:
            skill_dist["0-25"] += 1
        elif s["score"] <= 50:
            skill_dist["26-50"] += 1
        elif s["score"] <= 75:
            skill_dist["51-75"] += 1
        else:
            skill_dist["76-100"] += 1

    lines.append("### Skills")
    lines.append("")
    lines.append("| Score Range | Count |")
    lines.append("|-------------|-------|")
    for range_str, count in skill_dist.items():
        bar = "█" * (count // 10) if count > 0 else ""
        lines.append(f"| {range_str}% | {count} {bar} |")
    lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Generate quality report")
    parser.add_argument(
        "--catalog",
        type=Path,
        default=CATALOG_PATH,
        help=f"Path to catalog.json (default: {CATALOG_PATH})",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=REPORT_JSON_PATH,
        help=f"Output path for JSON report (default: {REPORT_JSON_PATH})",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=REPORT_MD_PATH,
        help=f"Output path for markdown report (default: {REPORT_MD_PATH})",
    )
    args = parser.parse_args()

    # Load catalog
    if not args.catalog.exists():
        print(f"Error: Catalog not found: {args.catalog}")
        return 1

    with open(args.catalog) as f:
        catalog = json.load(f)

    print(f"Generating quality report from {args.catalog}...")

    # Generate report
    report = generate_quality_report(catalog)

    # Save JSON
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_json, "w") as f:
        json.dump(report, f, indent=2)
    print(f"  JSON report: {args.out_json}")

    # Save markdown
    md_report = generate_markdown_report(report)
    with open(args.out_md, "w") as f:
        f.write(md_report)
    print(f"  Markdown report: {args.out_md}")

    # Print summary
    summary = report["summary"]
    print(f"\nQuality Summary:")
    print(f"  Avg Plugin Score: {summary['avg_plugin_score']}%")
    print(f"  Avg Skill Score:  {summary['avg_skill_score']}%")
    print(f"  Plugins < 50%:    {summary['plugins_below_50']}")
    print(f"  Skills < 50%:     {summary['skills_below_50']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
