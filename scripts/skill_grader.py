#!/usr/bin/env python3
"""
Skill Quality Grader - Intent Solutions 100-Point Rubric

Extracted from claude-code-plugins/scripts/validate-skills-schema.py

Based on:
- Anthropic Official Best Practices (platform.claude.com/docs)
- Lee Han Chung Deep Dive (leehanchung.github.io)
- Intent Solutions production grading at scale

Grade Scale:
    A (90-100): Production-ready
    B (80-89):  Good, minor improvements needed
    C (70-79):  Adequate, has gaps
    D (60-69):  Needs significant work
    F (<60):    Major revision required
"""

import re
from pathlib import Path
from typing import Any


# Required sections for Nixtla quality standard
REQUIRED_SECTIONS = [
    "## Overview",
    "## Prerequisites",
    "## Instructions",
    "## Output",
    "## Error Handling",
    "## Examples",
    "## Resources",
]

CODE_FENCE_PATTERN = re.compile(r"^\s*(```|~~~)")


def calculate_grade(score: int) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return 'A'
    elif score >= 80:
        return 'B'
    elif score >= 70:
        return 'C'
    elif score >= 60:
        return 'D'
    else:
        return 'F'


def score_progressive_disclosure(path: Path, body: str, fm: dict) -> dict:
    """
    Progressive Disclosure Architecture (30 pts max)
    - Token Economy (10): SKILL.md line count
    - Layered Structure (10): Has references/ directory with content
    - Reference Depth (5): References are one level deep only
    - Navigation Signals (5): Has TOC for long files
    """
    breakdown = {}
    lines = len(body.splitlines())
    skill_dir = path.parent

    # Token Economy (10 pts)
    if lines <= 150:
        breakdown['token_economy'] = (10, "Excellent: <=150 lines")
    elif lines <= 300:
        breakdown['token_economy'] = (5, f"Acceptable: {lines} lines")
    else:
        breakdown['token_economy'] = (0, f"Too long: {lines} lines")

    # Layered Structure (10 pts)
    refs_dir = skill_dir / "references"
    if refs_dir.exists():
        ref_files = list(refs_dir.glob("*.md"))
        if ref_files:
            breakdown['layered_structure'] = (10, f"Has references/ with {len(ref_files)} files")
        else:
            breakdown['layered_structure'] = (3, "references/ exists but empty")
    else:
        if lines <= 100:
            breakdown['layered_structure'] = (8, "No references/ (acceptable for short skill)")
        elif lines <= 200:
            breakdown['layered_structure'] = (4, "No references/ (should extract content)")
        else:
            breakdown['layered_structure'] = (0, "No references/ (long skill needs extraction)")

    # Reference Depth (5 pts)
    if refs_dir.exists():
        nested_dirs = [d for d in refs_dir.iterdir() if d.is_dir()]
        if not nested_dirs:
            breakdown['reference_depth'] = (5, "References are flat")
        else:
            breakdown['reference_depth'] = (2, f"Nested dirs: {len(nested_dirs)}")
    else:
        breakdown['reference_depth'] = (5, "N/A")

    # Navigation Signals (5 pts)
    has_toc = bool(re.search(r'(?mi)^##?\s*(table of contents|contents|toc)\b', body))
    has_nav_links = bool(re.search(r'\[.*?\]\(#.*?\)', body))
    if lines <= 100:
        breakdown['navigation_signals'] = (5, "Short file, TOC optional")
    elif has_toc or has_nav_links:
        breakdown['navigation_signals'] = (5, "Has navigation/TOC")
    else:
        breakdown['navigation_signals'] = (0, "Long file needs TOC")

    total = sum(v[0] for v in breakdown.values())
    return {'score': total, 'max': 30, 'breakdown': breakdown}


def score_ease_of_use(path: Path, body: str, fm: dict) -> dict:
    """
    Ease of Use (25 pts max)
    - Metadata Quality (10): Complete, well-formed frontmatter
    - Discoverability (6): Has trigger phrases, "Use when"
    - Terminology Consistency (4): Consistent naming
    - Workflow Clarity (5): Clear step-by-step instructions
    """
    breakdown = {}
    desc = str(fm.get('description', '')).lower()

    # Metadata Quality (10 pts)
    meta_score = 0
    meta_notes = []
    if fm.get('name'):
        meta_score += 2
    else:
        meta_notes.append("missing name")
    if fm.get('description') and len(str(fm.get('description', ''))) >= 50:
        meta_score += 3
    else:
        meta_notes.append("description too short")
    if fm.get('version'):
        meta_score += 2
    else:
        meta_notes.append("missing version")
    if fm.get('allowed-tools'):
        meta_score += 2
    else:
        meta_notes.append("missing allowed-tools")
    if fm.get('author') and '@' in str(fm.get('author', '')):
        meta_score += 1
    breakdown['metadata_quality'] = (meta_score, ", ".join(meta_notes) if meta_notes else "Complete")

    # Discoverability (6 pts)
    disc_score = 0
    disc_notes = []
    if 'use when' in desc:
        disc_score += 3
        disc_notes.append("has 'Use when'")
    if 'trigger with' in desc or 'trigger phrase' in desc:
        disc_score += 3
        disc_notes.append("has trigger phrases")
    if not disc_notes:
        disc_notes.append("missing discovery cues")
    breakdown['discoverability'] = (disc_score, ", ".join(disc_notes))

    # Terminology Consistency (4 pts)
    name = str(fm.get('name', ''))
    folder = path.parent.name
    term_score = 4
    term_notes = []
    if name and name != folder:
        term_score -= 2
        term_notes.append("name differs from folder")
    breakdown['terminology'] = (max(0, term_score), ", ".join(term_notes) if term_notes else "Consistent")

    # Workflow Clarity (5 pts)
    workflow_score = 0
    workflow_notes = []
    if re.search(r'(?m)^\s*1\.\s+', body):
        workflow_score += 3
        workflow_notes.append("has numbered steps")
    section_count = len(re.findall(r'(?m)^##\s+', body))
    if section_count >= 5:
        workflow_score += 2
        workflow_notes.append(f"{section_count} sections")
    elif section_count >= 3:
        workflow_score += 1
        workflow_notes.append(f"{section_count} sections")
    if not workflow_notes:
        workflow_notes.append("unclear workflow")
    breakdown['workflow_clarity'] = (workflow_score, ", ".join(workflow_notes))

    total = sum(v[0] for v in breakdown.values())
    return {'score': total, 'max': 25, 'breakdown': breakdown}


def score_utility(path: Path, body: str, fm: dict) -> dict:
    """
    Utility (20 pts max)
    - Problem Solving Power (8): Clear use cases, practical value
    - Degrees of Freedom (5): Flexible, configurable
    - Feedback Loops (4): Error handling, validation
    - Examples & Templates (3): Has working examples
    """
    breakdown = {}
    body_lower = body.lower()

    # Problem Solving Power (8 pts)
    problem_score = 0
    problem_notes = []
    if '## overview' in body_lower:
        overview_match = re.search(r'## overview\s*\n(.*?)(?=\n##|\Z)', body, re.IGNORECASE | re.DOTALL)
        if overview_match and len(overview_match.group(1).strip()) > 50:
            problem_score += 4
            problem_notes.append("has overview")
    if '## prerequisites' in body_lower:
        problem_score += 2
        problem_notes.append("has prerequisites")
    if '## output' in body_lower:
        problem_score += 2
        problem_notes.append("has output spec")
    if not problem_notes:
        problem_notes.append("unclear problem/solution")
    breakdown['problem_solving'] = (problem_score, ", ".join(problem_notes))

    # Degrees of Freedom (5 pts)
    freedom_score = 0
    freedom_notes = []
    if re.search(r'(?i)(optional|configur|parameter|argument|flag|option)', body):
        freedom_score += 2
        freedom_notes.append("has options")
    if re.search(r'(?i)(alternatively|or use|another approach)', body):
        freedom_score += 2
        freedom_notes.append("shows alternatives")
    if re.search(r'(?i)(extend|customize|modify|adapt)', body):
        freedom_score += 1
        freedom_notes.append("extensible")
    if not freedom_notes:
        freedom_notes.append("rigid implementation")
    breakdown['degrees_of_freedom'] = (freedom_score, ", ".join(freedom_notes))

    # Feedback Loops (4 pts)
    feedback_score = 0
    feedback_notes = []
    if '## error handling' in body_lower:
        feedback_score += 2
        feedback_notes.append("has error handling")
    if re.search(r'(?i)(validate|verify|check|test|confirm)', body):
        feedback_score += 1
        feedback_notes.append("has validation")
    if re.search(r'(?i)(troubleshoot|debug|diagnose|fix)', body):
        feedback_score += 1
        feedback_notes.append("has troubleshooting")
    if not feedback_notes:
        feedback_notes.append("no feedback mechanisms")
    breakdown['feedback_loops'] = (feedback_score, ", ".join(feedback_notes))

    # Examples & Templates (3 pts)
    examples_score = 0
    examples_notes = []
    if '## examples' in body_lower or '**example' in body_lower:
        examples_score += 2
        examples_notes.append("has examples")
    if '```' in body:
        code_blocks = len(re.findall(r'```', body)) // 2
        if code_blocks >= 2:
            examples_score += 1
            examples_notes.append(f"{code_blocks} code blocks")
    if not examples_notes:
        examples_notes.append("no examples")
    breakdown['examples'] = (examples_score, ", ".join(examples_notes))

    total = sum(v[0] for v in breakdown.values())
    return {'score': total, 'max': 20, 'breakdown': breakdown}


def score_spec_compliance(path: Path, body: str, fm: dict) -> dict:
    """
    Spec Compliance (15 pts max)
    - Frontmatter Validity (5): Valid YAML, no parse errors
    - Name Conventions (4): Kebab-case, proper length
    - Description Quality (4): Proper length, no forbidden words
    - Optional Fields (2): Proper use of optional fields
    """
    breakdown = {}
    name = str(fm.get('name', ''))
    desc = str(fm.get('description', ''))

    # Frontmatter Validity (5 pts)
    fm_score = 5
    fm_notes = []
    required = {'name', 'description', 'allowed-tools', 'version', 'author', 'license'}
    missing = required - set(fm.keys())
    if missing:
        fm_score -= min(len(missing), 4)
        fm_notes.append(f"missing: {len(missing)}")
    if not fm_notes:
        fm_notes.append("valid frontmatter")
    breakdown['frontmatter_validity'] = (max(0, fm_score), ", ".join(fm_notes))

    # Name Conventions (4 pts)
    name_score = 4
    name_notes = []
    if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$', name) and len(name) > 1:
        name_score -= 2
        name_notes.append("not kebab-case")
    if len(name) > 64:
        name_score -= 1
        name_notes.append("name too long")
    if name != path.parent.name:
        name_score -= 1
        name_notes.append("name/folder mismatch")
    if not name_notes:
        name_notes.append("proper naming")
    breakdown['name_conventions'] = (max(0, name_score), ", ".join(name_notes))

    # Description Quality (4 pts)
    desc_score = 4
    desc_notes = []
    if len(desc) < 50:
        desc_score -= 2
        desc_notes.append("too short")
    if len(desc) > 1024:
        desc_score -= 2
        desc_notes.append("too long")
    desc_lower = desc.lower()
    if 'i can' in desc_lower or 'i will' in desc_lower:
        desc_score -= 1
        desc_notes.append("uses first person")
    if not desc_notes:
        desc_notes.append("good description")
    breakdown['description_quality'] = (max(0, desc_score), ", ".join(desc_notes))

    # Optional Fields (2 pts)
    opt_score = 2
    opt_notes = []
    if 'model' in fm:
        model = fm['model']
        if model not in ['inherit', 'sonnet', 'haiku'] and not str(model).startswith('claude-'):
            opt_score -= 1
            opt_notes.append("invalid model")
    if not opt_notes:
        opt_notes.append("optional fields ok")
    breakdown['optional_fields'] = (opt_score, ", ".join(opt_notes))

    total = sum(v[0] for v in breakdown.values())
    return {'score': total, 'max': 15, 'breakdown': breakdown}


def score_writing_style(path: Path, body: str, fm: dict) -> dict:
    """
    Writing Style (10 pts max)
    - Voice & Tense (4): Imperative voice, present tense
    - Objectivity (3): No first/second person in body
    - Conciseness (3): Not overly verbose
    """
    breakdown = {}

    # Voice & Tense (4 pts)
    voice_score = 4
    voice_notes = []
    imperative_verbs = ['create', 'use', 'run', 'execute', 'configure', 'set', 'add', 'remove', 'check', 'verify']
    has_imperative = any(re.search(rf'(?m)^\s*\d+\.\s*{v}', body, re.IGNORECASE) for v in imperative_verbs)
    if not has_imperative:
        voice_score -= 2
        voice_notes.append("use imperative voice")
    if not voice_notes:
        voice_notes.append("good voice")
    breakdown['voice_tense'] = (voice_score, ", ".join(voice_notes))

    # Objectivity (3 pts)
    obj_score = 3
    obj_notes = []
    body_lower = body.lower()
    if 'you should' in body_lower or 'you can' in body_lower:
        obj_score -= 1
        obj_notes.append("has second person")
    if ' i ' in body_lower or 'i can' in body_lower:
        obj_score -= 1
        obj_notes.append("has first person")
    if not obj_notes:
        obj_notes.append("objective")
    breakdown['objectivity'] = (max(0, obj_score), ", ".join(obj_notes))

    # Conciseness (3 pts)
    conc_score = 3
    conc_notes = []
    word_count = len(body.split())
    lines = len(body.splitlines())
    if word_count > 3000:
        conc_score -= 2
        conc_notes.append(f"verbose ({word_count} words)")
    elif word_count > 2000:
        conc_score -= 1
        conc_notes.append(f"lengthy ({word_count} words)")
    if lines > 400:
        conc_score -= 1
        conc_notes.append(f"many lines ({lines})")
    if not conc_notes:
        conc_notes.append("concise")
    breakdown['conciseness'] = (max(0, conc_score), ", ".join(conc_notes))

    total = sum(v[0] for v in breakdown.values())
    return {'score': total, 'max': 10, 'breakdown': breakdown}


def calculate_modifiers(path: Path, body: str, fm: dict) -> dict:
    """
    Modifiers (+/- pts)
    Bonuses: gerund name, grep-friendly, exemplary examples
    Penalties: first/second person description, no TOC on long file
    """
    modifiers = {}
    name = str(fm.get('name', ''))
    desc = str(fm.get('description', ''))
    lines = len(body.splitlines())

    # Bonuses
    if name.endswith('ing'):
        modifiers['gerund_name'] = (+1, "gerund-style name")

    sections = len(re.findall(r'(?m)^##\s+', body))
    if sections >= 7:
        modifiers['grep_friendly'] = (+1, "grep-friendly structure")

    example_count = len(re.findall(r'(?i)\*\*example[:\s]', body))
    if example_count >= 3:
        modifiers['exemplary_examples'] = (+2, f"{example_count} labeled examples")

    if '## resources' in body.lower():
        external_links = len(re.findall(r'\[.*?\]\(https?://', body))
        if external_links >= 2:
            modifiers['external_resources'] = (+1, f"{external_links} external links")

    # Penalties
    desc_lower = desc.lower()
    if 'i can' in desc_lower or 'i will' in desc_lower or 'you can' in desc_lower:
        modifiers['person_in_desc'] = (-2, "first/second person in description")

    has_toc = bool(re.search(r'(?mi)^##?\s*(table of contents|contents|toc)\b', body))
    if lines > 150 and not has_toc:
        modifiers['missing_toc'] = (-2, "long file needs TOC")

    if '<' in body and '>' in body and re.search(r'<[a-z]+>', body):
        modifiers['xml_tags'] = (-1, "XML-like tags in body")

    total = sum(v[0] for v in modifiers.values())
    total = max(-15, min(15, total))  # Cap at +/-15
    return {'score': total, 'max_bonus': 5, 'max_penalty': -5, 'items': modifiers}


def grade_skill(path: Path, frontmatter: dict, body: str) -> dict:
    """
    Calculate Intent Solutions 100-point grade for a skill.

    Args:
        path: Path to SKILL.md file
        frontmatter: Parsed YAML frontmatter dict
        body: Markdown body content (after frontmatter)

    Returns:
        dict with:
        - score: total points (0-100)
        - grade: letter grade (A-F)
        - breakdown: per-pillar scores
    """
    pda = score_progressive_disclosure(path, body, frontmatter)
    ease = score_ease_of_use(path, body, frontmatter)
    utility = score_utility(path, body, frontmatter)
    spec = score_spec_compliance(path, body, frontmatter)
    style = score_writing_style(path, body, frontmatter)
    mods = calculate_modifiers(path, body, frontmatter)

    base_score = pda['score'] + ease['score'] + utility['score'] + spec['score'] + style['score']
    total_score = base_score + mods['score']

    # Clamp to 0-100
    total_score = max(0, min(100, total_score))

    return {
        'score': total_score,
        'grade': calculate_grade(total_score),
        'breakdown': {
            'progressive_disclosure': pda['score'],
            'ease_of_use': ease['score'],
            'utility': utility['score'],
            'spec_compliance': spec['score'],
            'writing_style': style['score'],
            'modifiers': mods['score'],
        }
    }


def get_missing_sections(body: str) -> list[str]:
    """Check which required sections are missing from the body."""
    body_lower = body.lower()
    missing = []
    for section in REQUIRED_SECTIONS:
        if section.lower() not in body_lower:
            missing.append(section)
    return missing
