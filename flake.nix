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

        pythonEnv = pkgs.python313.withPackages (
          ps: with ps; [
            # Core crawling
            httpx
            aiohttp
            aiosqlite
            pydantic

            # Web automation (crawlee substitute)
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

            # ML & Vision (Phase 1 - no PyTorch yet, will add in Phase 2)
            # pytorch torchvision transformers (Phase 2)
            scikit-learn
            numpy
            pandas
            scipy

            # Orchestration (Phase 2)
            # prefect (Phase 2)

            # Dev
            pytest
            pytest-asyncio
            pytest-cov
            ruff
            mypy
            bandit
            pip
          ]
        );

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
            echo "  just test-cov           Run tests with coverage"
            echo "  just hooks-install      Install pre-commit hooks"
            echo "  just security           Run security scans"
            echo "  just typecheck          Run type checking"
            echo "  just ci-local           Simulate full CI locally"
            echo "  just run <url>          Run crawler"
            echo "  just proxies            Fetch proxies"
            echo "  just clean              Clean artifacts"
            echo ""
            echo "Network Proxy:"
            echo "  cd ../spider-nix-network && go run ./cmd/spider-network-proxy"
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

          propagatedBuildInputs = with pkgs.python313Packages; [
            # Core HTTP/async
            httpx
            aiohttp
            aiosqlite
            pydantic

            # Web automation (crawlee substitute)
            playwright

            # OSINT
            aiodns
            pycares
            python-whois

            # CLI
            typer
            rich
            fake-useragent

            # Multimodal extraction
            lxml
            beautifulsoup4
            pillow

            # ML & Science
            scikit-learn
            numpy
            pandas
            scipy
          ];

          meta = with pkgs.lib; {
            description = "Enterprise web crawler for public data collection";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };
      }
    );
}
