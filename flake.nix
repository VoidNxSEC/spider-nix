{
  description = "SpiderNix - Enterprise web crawler for public data collection";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
    }:
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = import nixpkgs { inherit system; };

        # Shared Python dependencies
        sharedDeps = with pkgs.python313Packages; [
          # Core crawling
          httpx
          aiohttp
          aiosqlite
          pydantic

          # Web automation
          playwright

          # OSINT
          aiodns
          pycares
          python-whois

          # CLI
          typer
          rich

          # Utils
          fake-useragent

          # Multimodal extraction
          lxml
          beautifulsoup4
          pillow

          # ML & Vision
          scikit-learn
          numpy
          pandas
          scipy

          # Dev tools
          pytest
          pytest-asyncio
          pytest-cov
          ruff
          mypy
          bandit
          pip
          # safety # Not found in nixpkgs
          # pip-audit # Not found in nixpkgs
        ];

        pythonEnv = pkgs.python313.withPackages (ps: sharedDeps);

      in
      {
        devShells.default = pkgs.mkShell {
          name = "spider-nix-dev";

          buildInputs = with pkgs; [
            pythonEnv
            playwright-driver.browsers
            nodePackages.npm
            just
            playwright

            uv
            pre-commit
            git

            # Go toolchain for spider-network-proxy
            go
            gopls
          ];

          shellHook = ''
            export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
            export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
            export PYTHONPATH="$PWD/src:$PYTHONPATH"

            # Warn if .venv exists, as we are using Nix
            if [ -d ".venv" ]; then
                echo "⚠️  .venv detected but ignored in favor of Nix environment."
                echo "   Run 'rm -rf .venv' to avoid confusion."
            fi

            echo "🕷️  SpiderNix Development Environment"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "Python: $(python --version)"
            echo "Just:   $(just --version)"
            echo "uv:     $(uv --version)"
            echo ""
            echo "Commands:"
            echo "  just test               Run tests"
            echo "  just test-cov           Run tests with coverage"
            echo "  just security           Run security scans"
            echo "  just typecheck          Run type checking"
            echo "  just run <url>          Run crawler"
            echo ""
            echo "Network Proxy:"
            echo "  just proxy-start        Start proxy server"
            echo "  just proxy-build        Build proxy binary"
          '';
        };

        packages.default = pkgs.python313Packages.buildPythonApplication {
          pname = "spider-nix";
          version = "0.1.0";
          format = "pyproject";

          src = ./.;

          nativeBuildInputs = with pkgs.python313Packages; [
            hatchling
          ];

          propagatedBuildInputs = sharedDeps;

          meta = with pkgs.lib; {
            description = "Enterprise web crawler for public data collection";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };

        packages.spider-network-proxy = pkgs.buildGoModule {
          pname = "spider-network-proxy";
          version = "0.1.0";

          src = ./network;

          vendorHash = null; # Will need to be set after go mod vendor

          meta = with pkgs.lib; {
            description = "Anti-detection HTTP/HTTPS proxy with TLS fingerprinting";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };
      }
    );
}
