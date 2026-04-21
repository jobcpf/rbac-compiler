# rbac-compiler

A Python CLI tool that compiles YAML-based RBAC registry files into an Ansible-applicable plan for a multi-tenant Linux fileserver classification system.

## Overview

Part of a wider agentic infrastructure system. The compiler reads a set of registry files describing organisations, data classifications, and agents, validates them, and emits a compiled plan (`compiled_plan.yml`) for Ansible to apply to the target fileserver.

**Pure transformation — makes no changes to any system.**

## Quick start

```bash
python3 -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"

# Validate registry
rbac-compile --registry-dir ~/registry --check

# Compile
rbac-compile --registry-dir ~/registry
```

## Status

`v0.1.0` — MVP. CLI + core compiler. GUI planned for v0.2.

## License

Private.
