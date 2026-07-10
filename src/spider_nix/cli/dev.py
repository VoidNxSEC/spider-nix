"""Development and CI tooling commands for SpiderNix."""

import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console

from spider_nix.server import start_server

console = Console()

TYPECHECK_TARGETS = [
    "src/spider_nix/config.py",
    "src/spider_nix/stealth.py",
    "src/spider_nix/browser.py",
    "src/spider_nix/ml/models.py",
    "src/spider_nix/ml/failure_classifier.py",
    "src/spider_nix/extraction/models.py",
    "src/spider_nix/extraction/fusion_engine.py",
    "src/spider_nix/osint/web_discovery.py",
    "src/spider_nix/osint/web_intelligence.py",
]


def _find_repo_root() -> Path:
    current = Path.cwd().resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "flake.nix").exists():
            return candidate
    console.print("[red]Could not locate repository root from the current directory.[/]")
    raise typer.Exit(1)


def _run_command(command: list[str], cwd: Path | None = None) -> None:
    """Run a repository workflow command and propagate its exit status."""
    repo_root = _find_repo_root()
    resolved_cwd = (repo_root / cwd) if cwd else repo_root
    result = subprocess.run(command, cwd=str(resolved_cwd), check=False)
    if result.returncode != 0:
        raise typer.Exit(result.returncode)


dev_app = typer.Typer(name="dev", help="Development and CI tooling")


@dev_app.command()
def version():
    """Show version."""
    from spider_nix import __version__

    console.print(f"[bold]SpiderNix v{__version__}[/]")


@dev_app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h"),
    port: int = typer.Option(8000, "--port", "-p"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """🌐 Start the web GUI."""
    console.print("\n[bold]🌐 Spider-Nix Web GUI[/]\n")
    console.print(f"   URL: http://{host}:{port}")
    console.print("   Press Ctrl+C to stop\n")
    start_server(host, port, open_browser=not no_browser)


@dev_app.command()
def test():
    """Run the test suite."""
    _run_command([sys.executable, "-m", "pytest", "tests/", "-v"])


@dev_app.command("test-cov")
def test_cov():
    """Run tests with coverage reporting."""
    _run_command(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "--cov=src/spider_nix",
            "--cov-report=html",
            "--cov-report=term",
        ]
    )


@dev_app.command()
def lint():
    """Run Ruff lint checks."""
    _run_command([sys.executable, "-m", "ruff", "check", "src/spider_nix"])


@dev_app.command()
def check():
    """Run the standard lint check."""
    lint()


@dev_app.command()
def fmt():
    """Format project code with Ruff."""
    _run_command([sys.executable, "-m", "ruff", "format", "src/spider_nix", "tests"])


@dev_app.command()
def typecheck():
    """Run mypy on the CI-stabilized module set."""
    _run_command(
        [
            sys.executable,
            "-m",
            "mypy",
            *TYPECHECK_TARGETS,
            "--ignore-missing-imports",
            "--follow-imports=skip",
        ]
    )


@dev_app.command()
def security():
    """Run security scans."""
    _run_command([sys.executable, "-m", "bandit", "-r", "src/spider_nix", "-ll"])


@dev_app.command("hooks-install")
def hooks_install():
    """Install pre-commit hooks."""
    _run_command(["pre-commit", "install"])


@dev_app.command("hooks-run")
def hooks_run():
    """Run pre-commit on all files."""
    _run_command(["pre-commit", "run", "--all-files"])


@dev_app.command()
def clean():
    """Clean local build and test artifacts."""
    repo_root = _find_repo_root()
    directories = [
        "build",
        "dist",
        ".pytest_cache",
        ".ruff_cache",
        "htmlcov",
    ]
    file_patterns = ["*.egg-info", "*.pyc"]

    for relative_path in directories:
        shutil.rmtree(repo_root / relative_path, ignore_errors=True)

    for pattern in file_patterns:
        for path in repo_root.glob(pattern):
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)

    for path in repo_root.rglob("__pycache__"):
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)

    console.print("[green]✓ Cleaned build and test artifacts[/]")


@dev_app.command("ci-local")
def ci_local():
    """Run the local CI command set."""
    lint()
    typecheck()
    security()
    test()


@dev_app.command("proxy-start")
def proxy_start():
    """Start the Go proxy server."""
    _run_command(
        ["go", "run", "./cmd/spider-network-proxy", "-config", "configs/test.toml"],
        cwd=Path("network"),
    )


@dev_app.command("proxy-build")
def proxy_build():
    """Build the Go proxy binary."""
    _run_command(
        ["go", "build", "-o", "../dist/spider-network-proxy", "./cmd/spider-network-proxy"],
        cwd=Path("network"),
    )


@dev_app.command()
def benchmark(
    url: str = typer.Argument(..., help="URL to benchmark"),
):
    """Benchmark crawl performance."""
    console.print(f"[cyan]Running performance benchmark on {url}[/]")
    _run_command(["hyperfine", "--warmup", "3", f"{sys.executable} -m spider_nix.cli crawl {url}"])
