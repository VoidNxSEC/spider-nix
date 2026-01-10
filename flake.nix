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
            httpx
            aiohttp
            aiosqlite
            pydantic
            aiodns
            pycares
            python-whois
            typer
            rich
            fake-useragent
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
