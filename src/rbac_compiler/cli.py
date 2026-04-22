"""
CLI entry point for rbac-compile.

Usage:
    rbac-compile [OPTIONS]
    python -m rbac_compiler [OPTIONS]
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

from . import __version__
from .compiler import compile_plan
from .emitter import emit
from .errors import RegistryLoadError
from .loader import discover_org_files, load_agent_registry, load_constants, load_org_file
from .validator import ValidationResult, validate_all

logger = logging.getLogger("rbac_compile")


def _setup_logging(verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(format="%(levelname)s: %(message)s", level=level, stream=sys.stderr)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--registry-dir", "-r",
    default=None,
    type=click.Path(path_type=Path),
    metavar="PATH",
    help="Registry directory. Default: ~/registry",
)
@click.option(
    "--output", "-o",
    default=None,
    type=click.Path(path_type=Path),
    metavar="PATH",
    help="Output file. Default: <registry-dir>/.compiled/compiled_plan.yml",
)
@click.option(
    "--check", "-c",
    is_flag=True,
    help="Validate only — do not write output. Exits 0 if valid.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Show detailed progress (INFO level).",
)
@click.option(
    "--quiet", "-q",
    is_flag=True,
    help="Suppress all output except errors.",
)
@click.option(
    "--format", "fmt",
    default="yaml",
    type=click.Choice(["yaml", "json"], case_sensitive=False),
    show_default=True,
    help="Output format.",
)
@click.version_option(version=__version__, prog_name="rbac-compile")
def cli(
    registry_dir: Path | None,
    output: Path | None,
    check: bool,
    verbose: bool,
    quiet: bool,
    fmt: str,
) -> None:
    """Compile RBAC registry YAML files into an Ansible-applicable plan.

    Reads classification_constants.yml, orgs/*.yml, and agent_registry.yml
    from the registry directory, validates them, and writes compiled_plan.yml.
    """
    _setup_logging(verbose, quiet)

    registry_dir = (registry_dir or Path.home() / "registry").expanduser().resolve()

    constants_path = registry_dir / "classification_constants.yml"
    agents_path = registry_dir / "agent_registry.yml"

    # ── Load ──────────────────────────────────────────────────────────────────
    try:
        constants, constants_hash = load_constants(constants_path)
        logger.info("Loaded constants: %s", constants_path)

        if output is None:
            output = registry_dir / constants.compiler.output_file

        agent_registry, agents_hash = load_agent_registry(agents_path)
        logger.info(
            "Loaded agent registry: %s (%d agents)", agents_path, len(agent_registry.agents)
        )

        org_paths = discover_org_files(registry_dir, constants.compiler.orgs_dir)
        if not org_paths:
            click.echo(
                f"WARN: No org files found in {registry_dir / constants.compiler.orgs_dir}",
                err=True,
            )

        org_files: list = []
        org_hashes: dict = {}
        for p in org_paths:
            org_file, org_hash = load_org_file(p)
            org_files.append((org_file, p))
            org_hashes[org_file.org] = org_hash
            logger.info("Loaded org file: %s (%d entries)", p, len(org_file.data))

    except RegistryLoadError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)

    # ── Validate ──────────────────────────────────────────────────────────────
    result: ValidationResult = validate_all(
        constants, constants_path, org_files, agent_registry, agents_path
    )

    for w in result.warnings:
        click.echo(f"WARN: {w}", err=True)

    if not result.ok:
        for e in result.errors:
            click.echo(f"ERROR: {e}", err=True)
        click.echo(
            f"\nValidation failed: {len(result.errors)} error(s), "
            f"{len(result.warnings)} warning(s).",
            err=True,
        )
        sys.exit(1)

    n_orgs = len(org_files)
    n_agents = len(agent_registry.agents)
    n_entries = sum(len(of.data) for of, _ in org_files)

    if check:
        if not quiet:
            click.echo(
                f"Validation passed: {n_orgs} org(s), {n_entries} data entries, {n_agents} agent(s)."
            )
        sys.exit(0)

    # ── Compile ───────────────────────────────────────────────────────────────
    try:
        plan = compile_plan(
            constants=constants,
            org_files=org_files,
            agent_registry=agent_registry,
            source_paths={
                "constants": str(constants_path),
                "agents": str(agents_path),
                "orgs": {of.org: str(p) for of, p in org_files},
            },
            source_hashes={
                "constants": constants_hash,
                "agents": agents_hash,
                "orgs": org_hashes,
            },
        )
    except Exception as exc:
        click.echo(f"CRITICAL: Internal compiler error: {exc}", err=True)
        sys.exit(3)

    # ── Emit ──────────────────────────────────────────────────────────────────
    assert output is not None
    try:
        emit(plan, output, fmt=fmt)
    except OSError as exc:
        click.echo(f"ERROR: Cannot write output: {exc}", err=True)
        sys.exit(2)

    if not quiet:
        click.echo(
            f"Compiled {len(plan.required_groups)} groups, "
            f"{len(plan.agent_users)} agents, "
            f"{len(plan.directory_classifications)} directories "
            f"-> {output}"
        )


def main() -> None:
    cli()
