"""
shared.llm.skill — skill definition loader and prompt renderer.

A skill is a directory containing:
  skill.yaml  — metadata: name, description, system prompt, inputs, output config
  prompt.md   — Jinja2 template rendered with a context dict before sending to LLM

The skill system is provider-agnostic. skill.yaml lists compatible_models for
reference but does NOT enforce which model is used — that's the caller's choice.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Template, StrictUndefined, UndefinedError


@dataclass
class SkillDef:
    name: str
    description: str
    system_prompt: str
    inputs: list[str]           # variable names expected in context dict
    max_tokens: int
    output_format: str          # "markdown" | "json" | "text"
    compatible_models: list[str]
    prompt_template: str        # raw Jinja2 template string


def load_skill(skill_dir: Path) -> SkillDef:
    """
    Load a skill from *skill_dir*.

    Raises FileNotFoundError if skill.yaml or prompt.md are missing.
    """
    meta_path = skill_dir / "skill.yaml"
    prompt_path = skill_dir / "prompt.md"

    if not meta_path.exists():
        raise FileNotFoundError(f"skill.yaml not found in {skill_dir}")
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt.md not found in {skill_dir}")

    with open(meta_path, encoding="utf-8") as fh:
        meta = yaml.safe_load(fh) or {}

    output = meta.get("output", {})

    return SkillDef(
        name=meta.get("name", skill_dir.name),
        description=meta.get("description", ""),
        system_prompt=meta.get("system_prompt", "You are a helpful assistant.").strip(),
        inputs=meta.get("inputs", []),
        max_tokens=output.get("max_tokens", 600),
        output_format=output.get("format", "markdown"),
        compatible_models=meta.get("compatible_models", []),
        prompt_template=prompt_path.read_text(encoding="utf-8"),
    )


def render_prompt(skill: SkillDef, context: dict) -> str:
    """
    Render the skill's Jinja2 prompt template with *context*.

    Raises UndefinedError if the template references a variable not in *context*.
    """
    try:
        return Template(
            skill.prompt_template,
            undefined=StrictUndefined,
        ).render(**context)
    except UndefinedError as exc:
        raise ValueError(
            f"Skill '{skill.name}' prompt template references undefined variable: {exc}"
        ) from exc
