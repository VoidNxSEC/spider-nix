{ pkgs ? import <nixpkgs> { } }:

let
  pythonEnv = pkgs.python313.withPackages (ps: with ps; [
    # Core crawling
    httpx
    aiohttp
    aiosqlite
    pydantic

    # OSINT
    aiodns
    pycares
    python-whois

    # CLI
    typer
    rich

    # Utils
    fake-useragent

    # Dev
    pytest
    pytest-asyncio
    ruff
    pip
  ]);
in
pkgs.mkShell {
  name = "spider-nix-dev";

  buildInputs = with pkgs; [
    pythonEnv
    playwright-driver.browsers
    nodePackages.npm
    just
    uv
  ];

  shellHook = ''
    export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
    export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
    export PYTHONPATH="$PWD/src:$PYTHONPATH"

    if [ -d ".venv" ]; then
        source .venv/bin/activate
    fi

    echo "🕷️  SpiderNix Development Environment"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Python: $(python --version)"
    echo "Just:   $(just --version)"
    echo "uv:     $(uv --version)"
    echo ""
    echo "Commands:"
    echo "  just install            Install spider-nix (editable)"
    echo "  just test               Run tests"
    echo "  just run <url>          Run crawler"
    echo "  just proxies            Fetch proxies"
    echo "  just clean              Clean artifacts"
  '';
}
