# rbac-compiler

Compiles YAML-based RBAC registry files into an Ansible-applicable plan for a multi-tenant Linux fileserver.

Reads `classification_constants.yml`, `orgs/*.yml`, and `agent_registry.yml` from a registry directory, validates them, and writes a `compiled_plan.yml` that Ansible consumes to create Linux groups, set directory ACLs, and configure agent users.

**Pure transformation — makes no changes to any system.**

## Requirements

- Python 3.10+
- `pipx` (recommended) or `pip`

## Installation

### From GitHub (recommended for production)

```bash
pipx install git+https://github.com/jobcpf/rbac-compiler.git
```

This installs the `rbac-compile` command into `~/.local/bin/` (in `$PATH` by default on Ubuntu 24.04). No virtualenv management needed.

To upgrade later:

```bash
pipx upgrade rbac-compiler
```

If `pipx` is not installed:

```bash
sudo apt install pipx
pipx ensurepath   # adds ~/.local/bin to PATH — restart shell afterwards
```

### For development (clone and edit)

```bash
git clone https://github.com/jobcpf/rbac-compiler.git
cd rbac-compiler
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

The `rbac-compile` command is then available inside the virtualenv. Use `source .venv/bin/activate` at the start of each session, or add the venv to your shell profile.

## Usage

```
rbac-compile [OPTIONS]
```

| Option | Short | Description |
|--------|-------|-------------|
| `--registry-dir PATH` | `-r` | Registry directory. Default: `~/ansible/registry` |
| `--output PATH` | `-o` | Output file. Default: `<registry-dir>/.compiled/compiled_plan.yml` |
| `--check` | `-c` | Validate only — do not write output. Exits 0 if valid. |
| `--format [yaml\|json]` | | Output format. Default: `yaml` |
| `--verbose` | `-v` | Show detailed progress. |
| `--quiet` | `-q` | Suppress all output except errors. |
| `--version` | | Print version and exit. |
| `--help` | `-h` | Show help and exit. |

### Examples

```bash
# Validate the registry at ~/registry (no output written)
rbac-compile --check

# Compile with defaults (registry at ~/registry, output at ~/registry/.compiled/compiled_plan.yml)
rbac-compile

# Use a custom registry directory
rbac-compile --registry-dir /opt/rbac-registry

# Validate a specific registry, verbose output
rbac-compile -r /opt/rbac-registry --check --verbose

# Write output to a specific file
rbac-compile --output /tmp/plan.yml

# JSON output (useful for inspection or piping to jq)
rbac-compile --format json --output /tmp/plan.json
```

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success (or `--check` passed) |
| `1` | Validation errors in registry files |
| `2` | File not found or I/O error |
| `3` | Internal compiler error |

## Registry layout

The compiler expects this structure under the registry directory:

```
~/registry/
  classification_constants.yml   # platform-wide constants and compiler config
  agent_registry.yml             # agent definitions and access grants
  orgs/
    arc.yml                      # ARC Power org definition + data classifications
    cpf.yml                      # Carbon Project Finance org definition + data
  .compiled/
    compiled_plan.yml            # written by the compiler (consumed by Ansible)
```

Adding a new organisation requires only dropping a new `.yml` file into `orgs/`.

## Output

`compiled_plan.yml` contains four sections:

- **`required_groups`** — all Linux groups that must exist on the fileserver. In v0.3 this is *data-driven*: only groups that at least one directory classifies to appear. Agent grants with wildcards no longer expand into a cartesian product of groups.
- **`agent_users`** — each agent's username, description, and the subset of `required_groups` their grants match (via the three match rules: grade hierarchy, symmetric vertical wildcard `any`, symmetric scope wildcard `global`).
- **`admin_users`** — pre-existing Linux users (declared in `classification_constants.yml` under `admins:`) that must be added to *every* group in `required_groups`. Useful for host accounts like `beaver` that need access to everything.
- **`directory_classifications`** — each classified path with its owning group and ACL mode.

Ansible reads this file and applies the state to the fileserver.

### Adding admin super-users

Add usernames to `classification_constants.yml`:

```yaml
admins:
  - beaver        # fileserver host account
  - ansi          # Ansible's own account
```

Ansible is responsible for ensuring the account exists (create if missing) and adding it to the groups specified. If `admins:` is omitted or empty, no admin entries appear in the plan. Rely on agents at `grade: 0, vertical: any, scope: global` instead.

## Development

```bash
# Run tests
pytest

# Run tests with coverage
pytest --cov

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

## Schema version

All registry files must carry `meta.version: "0.3"`. The compiler rejects files with a mismatched version and emits an operator-facing migration message for v0.2 layouts. The expected version is configured in `classification_constants.yml` under `compiler.schema_version`.

See [RBAC_Compiler_v0_3_Brief.md](../RBAC_Compiler_v0_3_Brief.md) for the authoritative spec.

## License

Private.
