"""
Writes the compiled plan to disk in YAML or JSON format.
Creates the output directory if it doesn't exist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.compat import StringIO

from .compiler import CompiledPlan


def _plan_to_dict(plan: CompiledPlan) -> dict[str, Any]:
    return {
        "meta": {
            "compiled_at": plan.compiled_at,
            "compiler_version": plan.compiler_version,
            "source_files": plan.source_files,
            "source_hashes": plan.source_hashes,
        },
        "required_groups": plan.required_groups,
        "agent_users": [
            {
                "name": au.name,
                "description": au.description,
                "groups": au.groups,
            }
            for au in plan.agent_users
        ],
        "directory_classifications": [
            {
                "path": dc.path,
                "group": dc.group,
                "mode": dc.mode,
                "apply_default_acl": dc.apply_default_acl,
                "description": dc.description,
                "source_file": dc.source_file,
            }
            for dc in plan.directory_classifications
        ],
    }


def emit(plan: CompiledPlan, output_path: Path, fmt: str = "yaml") -> None:
    """Write the compiled plan to output_path. Creates parent directories as needed."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = _plan_to_dict(plan)

    if fmt == "json":
        output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    else:
        yaml = YAML()
        yaml.default_flow_style = False
        yaml.width = 120  # type: ignore[assignment]
        stream = StringIO()
        yaml.dump(data, stream)
        output_path.write_text(stream.getvalue(), encoding="utf-8")
