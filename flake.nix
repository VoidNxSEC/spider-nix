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

          # Web GUI
          fastapi
          uvicorn
          jinja2

          # Multimodal extraction
          lxml
          beautifulsoup4
          pillow
          defusedxml

          # ML & Vision
          scikit-learn
          numpy
          pandas
          scipy

          # Dev tools
          pytest
          pytest-asyncio
          pytest-cov
          pytest-httpx
          ruff
          mypy
          bandit
          build
          pip
          pypdf
          # safety # Not found in nixpkgs
          # pip-audit # Not found in nixpkgs
        ];

        pythonEnv = pkgs.python313.withPackages (ps: sharedDeps);
        spiderCli = pkgs.writeShellApplication {
          name = "spider";
          runtimeInputs = [ pythonEnv ];
          text = ''
            repo_root="$PWD"
            while [ "$repo_root" != "/" ]; do
              if [ -f "$repo_root/pyproject.toml" ] && [ -f "$repo_root/flake.nix" ]; then
                break
              fi
              repo_root="$(dirname "$repo_root")"
            done

            if [ ! -f "$repo_root/pyproject.toml" ] || [ ! -f "$repo_root/flake.nix" ]; then
              echo "spider: could not locate repository root from $PWD" >&2
              exit 1
            fi

            export PYTHONPATH="$repo_root/src:$PYTHONPATH"
            cd "$repo_root"
            exec python -c 'from spider_nix.cli import app; app(prog_name="spider")' "$@"
          '';
        };

      in
      {
        devShells.default = pkgs.mkShell {
          name = "spider-nix-dev";

          buildInputs = with pkgs; [
            pythonEnv
            playwright-driver.browsers
            nodejs_24
            just
            playwright
            hyperfine
            spiderCli
            httpx

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

                        sp() {
                          spider "$@"
                        }

                        spider-help() {
                          cat <<'EOF'
            SpiderNix Dev Commands
              spider crawl <url>       Crawl a target
              spider recon <module>    Run OSINT and web recon commands
              spider test              Run the test suite
              spider test-cov          Run tests with coverage output
              spider check             Run Ruff lint checks
              spider fmt               Format code with Ruff
              spider typecheck         Run mypy
              spider security          Run Bandit
              spider ci-local          Run the local validation chain
              spider proxy-start       Start the Go proxy
              spider proxy-build       Build the Go proxy
              spider clean             Remove local build and test artifacts

            Shortcuts
              sp <args>                Shortcut for spider <args>
              spider-help              Print this reference
            EOF
                        }

                        case "$-" in
                          *i*)
                            if [ -n "$ZSH_VERSION" ]; then
                              eval "$(env _SPIDER_COMPLETE=zsh_source spider)"
                            elif [ -n "$BASH_VERSION" ]; then
                              eval "$(env _SPIDER_COMPLETE=bash_source spider)"
                            fi
                            ;;
                        esac

                        # Warn if .venv exists, as we are using Nix
                        if [ -d ".venv" ]; then
                            echo "⚠️  .venv detected but ignored in favor of Nix environment."
                            echo "   Run 'rm -rf .venv' to avoid confusion."
                        fi

                        cat <<'EOF'

               _____       _     _           _   __ _
              / ____|     (_)   | |         | | / /(_)
             | (___  _ __  _  __| | ___ _ __| |/ /  ___  __
              \___ \| '_ \| |/ _` |/ _ \ '__|    \ | \ \/ /
              ____) | |_) | | (_| |  __/ |  | |\  \| |>  <
             |_____/| .__/|_|\__,_|\___|_|  |_| \_\_/_/\_\
                    | |
                    |_|   Dev Shell

            Helper  : sp -> spider

            Core Commands
              spider crawl <url>       Crawl a target
              spider serve             Start web GUI (localhost:8000)
              spider recon --help      Explore recon modules
              spider job --help        Job hunt, track, autofill
              spider status            Quick dashboard

            Dev Tools
              spider test              Run tests
              spider test-cov          Run tests with coverage
              spider check             Run lint checks
              spider fmt               Format code
              spider typecheck         Run mypy
              spider security          Run Bandit
              spider ci-local          Run the local validation chain

            Proxy
              spider proxy-start       Start proxy server
              spider proxy-build       Build proxy binary

            Tips
              spider --help            Full command reference
              spider-help              Compact dev cheat sheet
              TAB on 'spider'          Completion with command descriptions
            EOF
                        echo "Python  : $(python --version)"
                        echo "Just    : $(just --version)"
                        echo "uv      : $(uv --version)"
          '';
        };

        formatter = pkgs.nixfmt;

        packages.default = pkgs.python313Packages.buildPythonApplication {
          pname = "spider-nix";
          version = "0.2.0";
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
          version = "0.0.1";

          src = ./network;

          vendorHash = "sha256-+7VzAIUCeBxlU5zVk6xPtzJhWfmtKdccRdTy7fnoIg0=";

          meta = with pkgs.lib; {
            description = "Anti-detection HTTP/HTTPS proxy with TLS fingerprinting";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };
      }
    );
}
