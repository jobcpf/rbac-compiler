"""
CLI entry point for rbac-compile.

Thin wrapper over rbac_compiler.operations — argument parsing, logging,
and human-readable formatting. Structured results come from operations.py.

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
from .errors import RegistryLoadError
from .operations import CompileResult, compile_registry
from .validator import ValidationResult

logger = logging.getLogger("rbac_compile")


def _setup_logging(verbose: bool, quiet: bool) -> None:
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.INFO
    else:
        level = logging.WARNING
    logging.basicConfig(format="%(levelname)s: %(message)s", level=level, stream=sys.stderr)


def _default_registry_dir() -> Path:
    return Path.home() / "registry"


def _print_warnings(validation: ValidationResult) -> None:
    for w in validation.warnings:
        click.echo(f"WARN: {w}", err=True)


def _print_errors(validation: ValidationResult) -> None:
    for e in validation.errors:
        click.echo(f"ERROR: {e}", err=True)
    click.echo(
        f"\nValidation failed: {len(validation.errors)} error(s), "
        f"{len(validation.warnings)} warning(s).",
        err=True,
    )


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
    reg_dir = (registry_dir or _default_registry_dir()).expanduser().resolve()

    try:
        result: CompileResult = compile_registry(
            registry_dir=reg_dir,
            output=output,
            fmt=fmt.lower(),
            check_only=check,
        )
    except RegistryLoadError as exc:
        click.echo(f"ERROR: {exc}", err=True)
        sys.exit(2)
    except OSError as exc:
        click.echo(f"ERROR: Cannot write output: {exc}", err=True)
        sys.exit(2)
    except Exception as exc:
        click.echo(f"CRITICAL: Internal compiler error: {exc}", err=True)
        sys.exit(3)

    _print_warnings(result.validation)

    if not result.validation.ok:
        _print_errors(result.validation)
        sys.exit(1)

    n_orgs = len(result.loaded.org_files)
    n_agents = len(result.loaded.agent_registry.agents)
    n_entries = sum(len(of.data) for of, _ in result.loaded.org_files)

    if check:
        if not quiet:
            click.echo(
                f"Validation passed: {n_orgs} org(s), {n_entries} data entries, {n_agents} agent(s)."
            )
        sys.exit(0)

    if result.plan is None or result.output_path is None:
        click.echo("ERROR: internal state: plan missing after validation passed", err=True)
        sys.exit(3)

    if not quiet:
        click.echo(
            f"Compiled {len(result.plan.required_groups)} groups, "
            f"{len(result.plan.agent_users)} agents, "
            f"{len(result.plan.admin_users)} admins, "
            f"{len(result.plan.directory_classifications)} directories "
            f"-> {result.output_path}"
        )


def main() -> None:
    cli()
