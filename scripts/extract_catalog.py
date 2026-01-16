#!/usr/bin/env python3
"""
Intent Catalog Extractor

Deterministic extraction of plugins, skills, and documents from repos.
Outputs catalog.json matching catalog.schema.json.

Usage:
    python extract_catalog.py --repo /path/to/ccpi --repo /path/to/nixtla --out dist/catalog.json
"""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = "1.0.0"

# Document type code mappings
DOC_TYPE_MAP = {
    "OD-ARCH": "architecture",
    "PP-PLAN": "planning",
    "PP-PRD": "spec",
    "PP-ARD": "decision",
    "AA-AACR": "report",
    "AA-AUDT": "audit",
    "DR-STND": "spec",
    "DR-GUID": "guide",
    "OD-REF": "reference",
    "OD-STAT": "report",
    "MC-MEMO": "report",
    "UC-CASE": "use_case",
}

# Filename pattern for numbered docs: NNN-AA-CODE-slug.md
DOC_PATTERN = re.compile(r"^(\d{3})-([A-Z]{2})-([A-Z]{4})-(.+)\.md$")


def get_git_commit(repo_path: Path) -> str:
    """Get current git commit hash."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()[:8]
    except subprocess.CalledProcessError:
        return "unknown"


def parse_yaml_frontmatter(content: str) -> tuple[dict, str]:
    """Extract YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    try:
        frontmatter = yaml.safe_load(parts[1]) or {}
        body = parts[2].strip()
        return frontmatter, body
    except yaml.YAMLError:
        return {}, content


def extract_trigger_phrases(description: str) -> list[str]:
    """Extract trigger phrases from skill description."""
    phrases = []
    # Look for "Trigger with" pattern
    match = re.search(r'[Tt]rigger\s+(?:with|on|using)\s+["\']?([^"\']+)["\']?', description)
    if match:
        # Split on commas or "or"
        raw = match.group(1)
        for phrase in re.split(r'[,"]|\s+or\s+', raw):
            phrase = phrase.strip().strip('"\'')
            if phrase and len(phrase) > 2:
                phrases.append(phrase)
    return sorted(set(phrases))


def to_kebab_case(s: str) -> str:
    """Convert string to kebab-case."""
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    return s.lower().strip("-")


def find_plugins(repo_path: Path, repo_name: str, commit: str, warnings: list) -> list[dict]:
    """Find all plugins in a repo."""
    plugins = []

    # Look for plugin manifests
    for manifest_path in repo_path.rglob("plugin.json"):
        try:
            plugin = extract_plugin(manifest_path, repo_path, repo_name, commit, warnings)
            if plugin:
                plugins.append(plugin)
        except Exception as e:
            warnings.append({
                "path": str(manifest_path.relative_to(repo_path)),
                "message": f"Failed to parse plugin: {e}",
                "severity": "error",
            })

    # Also check .claude-plugin/plugin.json
    for manifest_path in repo_path.rglob(".claude-plugin/plugin.json"):
        try:
            plugin = extract_plugin(manifest_path, repo_path, repo_name, commit, warnings)
            if plugin:
                # Avoid duplicates
                if not any(p["plugin_id"] == plugin["plugin_id"] for p in plugins):
                    plugins.append(plugin)
        except Exception as e:
            warnings.append({
                "path": str(manifest_path.relative_to(repo_path)),
                "message": f"Failed to parse plugin: {e}",
                "severity": "error",
            })

    return plugins


def extract_plugin(manifest_path: Path, repo_path: Path, repo_name: str, commit: str, warnings: list) -> dict | None:
    """Extract plugin info from manifest."""
    with open(manifest_path) as f:
        manifest = json.load(f)

    # Determine plugin directory
    if manifest_path.parent.name == ".claude-plugin":
        plugin_dir = manifest_path.parent.parent
    else:
        plugin_dir = manifest_path.parent

    plugin_id = to_kebab_case(manifest.get("name", plugin_dir.name))
    rel_path = str(plugin_dir.relative_to(repo_path))

    # Check for MCP
    has_mcp = (plugin_dir / ".mcp.json").exists()

    # Find commands
    commands = []
    commands_dir = plugin_dir / "commands"
    if commands_dir.exists():
        for cmd_file in commands_dir.glob("*.md"):
            commands.append(cmd_file.stem)

    # Find agents
    agents = []
    agents_dir = plugin_dir / "agents"
    if agents_dir.exists():
        for agent_file in agents_dir.glob("*.md"):
            agents.append(agent_file.stem)

    # Infer status
    status = "development"
    if "005-plugins" in rel_path or "production" in rel_path.lower():
        status = "production"
    elif "archive" in rel_path.lower():
        status = "archived"

    return {
        "plugin_id": plugin_id,
        "name": manifest.get("displayName", manifest.get("name", plugin_dir.name)),
        "description": manifest.get("description", ""),
        "version": manifest.get("version", ""),
        "path": rel_path,
        "source_repo": repo_name,
        "source_commit": commit,
        "status": status,
        "has_mcp": has_mcp,
        "commands": sorted(commands),
        "agents": sorted(agents),
    }


def find_skills(repo_path: Path, repo_name: str, commit: str, plugins: list[dict], warnings: list) -> tuple[list[dict], list[dict]]:
    """Find all skills in a repo."""
    skills = []
    relationships = []

    # Build plugin path lookup
    plugin_paths = {p["path"]: p["plugin_id"] for p in plugins}

    for skill_md in repo_path.rglob("SKILL.md"):
        try:
            skill, rels = extract_skill(skill_md, repo_path, repo_name, commit, plugin_paths, warnings)
            if skill:
                skills.append(skill)
                relationships.extend(rels)
        except Exception as e:
            warnings.append({
                "path": str(skill_md.relative_to(repo_path)),
                "message": f"Failed to parse skill: {e}",
                "severity": "error",
            })

    return skills, relationships


def extract_skill(skill_md: Path, repo_path: Path, repo_name: str, commit: str, plugin_paths: dict, warnings: list) -> tuple[dict | None, list[dict]]:
    """Extract skill info from SKILL.md."""
    content = skill_md.read_text()
    frontmatter, body = parse_yaml_frontmatter(content)

    if not frontmatter:
        warnings.append({
            "path": str(skill_md.relative_to(repo_path)),
            "message": "Missing YAML frontmatter",
            "severity": "warning",
        })

    skill_dir = skill_md.parent
    rel_path = str(skill_md.relative_to(repo_path))

    # Determine skill_id
    skill_id = to_kebab_case(frontmatter.get("name", skill_dir.name))

    # Check if inside a plugin
    is_standalone = True
    parent_plugin_id = None
    for plugin_path, plugin_id in plugin_paths.items():
        if rel_path.startswith(plugin_path):
            is_standalone = False
            parent_plugin_id = plugin_id
            break

    # Extract trigger phrases
    description = frontmatter.get("description", "")
    trigger_phrases = extract_trigger_phrases(description)

    skill = {
        "skill_id": skill_id,
        "name": frontmatter.get("name", skill_dir.name),
        "description": description,
        "version": frontmatter.get("version", ""),
        "path": rel_path,
        "source_repo": repo_name,
        "source_commit": commit,
        "allowed_tools": frontmatter.get("allowed-tools", ""),
        "author": frontmatter.get("author", ""),
        "license": frontmatter.get("license", ""),
        "trigger_phrases": trigger_phrases,
        "is_standalone": is_standalone,
        "has_references": (skill_dir / "references").exists(),
        "has_assets": (skill_dir / "assets").exists(),
        "has_scripts": (skill_dir / "scripts").exists(),
    }

    # Create relationship if inside plugin
    relationships = []
    if parent_plugin_id:
        relationships.append({
            "source_type": "plugin",
            "source_id": parent_plugin_id,
            "target_type": "skill",
            "target_id": skill_id,
            "relation_type": "ships_with",
            "confidence": "inferred",
        })

    return skill, relationships


def find_documents(repo_path: Path, repo_name: str, commit: str, warnings: list) -> list[dict]:
    """Find all documents in a repo."""
    documents = []
    seen_ids = set()

    # Find 000-docs directories
    for docs_dir in repo_path.rglob("000-docs"):
        if not docs_dir.is_dir():
            continue
        for doc_file in docs_dir.glob("*.md"):
            doc = extract_document(doc_file, repo_path, repo_name, commit, warnings)
            if doc and doc["doc_id"] not in seen_ids:
                documents.append(doc)
                seen_ids.add(doc["doc_id"])

    # Find pattern-matching docs anywhere
    for md_file in repo_path.rglob("*.md"):
        if DOC_PATTERN.match(md_file.name):
            doc = extract_document(md_file, repo_path, repo_name, commit, warnings)
            if doc and doc["doc_id"] not in seen_ids:
                documents.append(doc)
                seen_ids.add(doc["doc_id"])

    return documents


def extract_document(doc_path: Path, repo_path: Path, repo_name: str, commit: str, warnings: list) -> dict | None:
    """Extract document info."""
    rel_path = str(doc_path.relative_to(repo_path))
    filename = doc_path.name

    # Try to extract doc_id and type from filename
    match = DOC_PATTERN.match(filename)
    if match:
        seq, cat1, code, slug = match.groups()
        doc_id = f"{seq}-{cat1}-{code}-{slug}"
        category_code = f"{cat1}-{code}"
        doc_type = DOC_TYPE_MAP.get(category_code, "unknown")
    else:
        # Generate doc_id from path
        doc_id = to_kebab_case(doc_path.stem)
        if not doc_id:
            doc_id = f"doc-{hash(rel_path) % 10000:04d}"
        category_code = ""
        doc_type = "unknown"

    # Try to extract title from content
    title = filename.replace(".md", "").replace("-", " ").title()
    try:
        content = doc_path.read_text()
        # Look for first H1
        h1_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if h1_match:
            title = h1_match.group(1).strip()
    except Exception:
        pass

    return {
        "doc_id": doc_id,
        "title": title,
        "doc_type": doc_type,
        "category_code": category_code,
        "path": rel_path,
        "source_repo": repo_name,
        "source_commit": commit,
        "status": "unknown",
    }


def extract_catalog(repo_paths: list[Path], output_path: Path) -> dict:
    """Main extraction function."""
    warnings = []
    all_plugins = []
    all_skills = []
    all_documents = []
    all_relationships = []
    repos_meta = []

    for repo_path in repo_paths:
        repo_path = repo_path.resolve()
        repo_name = repo_path.name
        commit = get_git_commit(repo_path)

        repos_meta.append({
            "path": str(repo_path),
            "name": repo_name,
            "commit": commit,
        })

        # Extract plugins
        plugins = find_plugins(repo_path, repo_name, commit, warnings)
        all_plugins.extend(plugins)

        # Extract skills (creates relationships to plugins)
        skills, rels = find_skills(repo_path, repo_name, commit, plugins, warnings)
        all_skills.extend(skills)
        all_relationships.extend(rels)

        # Extract documents
        documents = find_documents(repo_path, repo_name, commit, warnings)
        all_documents.extend(documents)

    # Sort everything for determinism
    all_plugins.sort(key=lambda x: x["plugin_id"])
    all_skills.sort(key=lambda x: x["skill_id"])
    all_documents.sort(key=lambda x: x["doc_id"])
    all_relationships.sort(key=lambda x: (x["source_id"], x["target_id"], x["relation_type"]))
    warnings.sort(key=lambda x: x["path"])

    catalog = {
        "meta": {
            "version": SCHEMA_VERSION,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "repos": repos_meta,
        },
        "plugins": all_plugins,
        "skills": all_skills,
        "documents": all_documents,
        "relationships": all_relationships,
        "warnings": warnings,
    }

    return catalog


CONFIG_PATH = Path(__file__).parent.parent / "config" / "catalog.sources.json"


def load_sources_config() -> dict | None:
    """Load repository sources from config file."""
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH) as f:
        return json.load(f)


def detect_collisions(catalog: dict) -> list[dict]:
    """Detect ID collisions across repos and report them."""
    collisions = []

    # Check plugins
    plugin_sources = {}
    for p in catalog["plugins"]:
        pid = p["plugin_id"]
        if pid in plugin_sources:
            collisions.append({
                "type": "plugin",
                "id": pid,
                "repos": [plugin_sources[pid], p["source_repo"]],
            })
        else:
            plugin_sources[pid] = p["source_repo"]

    # Check skills
    skill_sources = {}
    for s in catalog["skills"]:
        sid = s["skill_id"]
        if sid in skill_sources:
            collisions.append({
                "type": "skill",
                "id": sid,
                "repos": [skill_sources[sid], s["source_repo"]],
            })
        else:
            skill_sources[sid] = s["source_repo"]

    # Check documents
    doc_sources = {}
    for d in catalog["documents"]:
        did = d["doc_id"]
        if did in doc_sources:
            collisions.append({
                "type": "document",
                "id": did,
                "repos": [doc_sources[did], d["source_repo"]],
            })
        else:
            doc_sources[did] = d["source_repo"]

    return collisions


def main():
    parser = argparse.ArgumentParser(description="Extract Intent Catalog from repos")
    parser.add_argument(
        "--repo",
        action="append",
        help="Path to repo (can be specified multiple times)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help=f"Path to sources config (default: {CONFIG_PATH})",
    )
    parser.add_argument(
        "--out",
        default="dist/catalog.json",
        help="Output path for catalog.json",
    )
    parser.add_argument(
        "--check-collisions",
        action="store_true",
        help="Check for ID collisions and fail if found",
    )
    args = parser.parse_args()

    # Determine repo paths from args or config
    repo_paths = []

    if args.repo:
        # Use explicit --repo arguments
        repo_paths = [Path(r) for r in args.repo]
    else:
        # Try loading from config
        config_path = args.config or CONFIG_PATH
        if config_path.exists():
            config = load_sources_config()
            if config:
                for source in config.get("sources", []):
                    if source.get("enabled", True) and source.get("type") == "local":
                        repo_paths.append(Path(source["path"]))
                print(f"Loaded {len(repo_paths)} repos from config")
        else:
            print(f"Error: No --repo specified and config not found: {config_path}")
            return 1

    if not repo_paths:
        print("Error: No repositories specified. Use --repo or create config/catalog.sources.json")
        return 1

    output_path = Path(args.out)

    # Validate repos exist
    valid_repos = []
    for repo in repo_paths:
        if not repo.exists():
            print(f"Warning: Repo path does not exist, skipping: {repo}")
        else:
            valid_repos.append(repo)

    if not valid_repos:
        print("Error: No valid repositories found")
        return 1

    # Extract
    catalog = extract_catalog(valid_repos, output_path)

    # Check for collisions
    collisions = detect_collisions(catalog)
    if collisions:
        print(f"\nWarning: Found {len(collisions)} ID collisions:")
        for c in collisions[:10]:
            print(f"  {c['type']} '{c['id']}' in repos: {', '.join(c['repos'])}")
        if len(collisions) > 10:
            print(f"  ... and {len(collisions) - 10} more")

        if args.check_collisions:
            print("\nFailing due to --check-collisions flag")
            return 1

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(catalog, f, indent=2, sort_keys=True)

    # Write warnings separately
    warnings_path = output_path.parent / "catalog.warnings.json"
    with open(warnings_path, "w") as f:
        json.dump(catalog["warnings"], f, indent=2)

    # Write collisions if any
    if collisions:
        collisions_path = output_path.parent / "catalog.collisions.json"
        with open(collisions_path, "w") as f:
            json.dump(collisions, f, indent=2)

    # Print summary
    print(f"\nExtracted catalog to {output_path}")
    print(f"  Plugins:       {len(catalog['plugins'])}")
    print(f"  Skills:        {len(catalog['skills'])}")
    print(f"  Documents:     {len(catalog['documents'])}")
    print(f"  Relationships: {len(catalog['relationships'])}")
    print(f"  Warnings:      {len(catalog['warnings'])}")
    if collisions:
        print(f"  Collisions:    {len(collisions)}")

    return 0


if __name__ == "__main__":
    exit(main())
