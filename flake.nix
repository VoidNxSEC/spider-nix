{
  description = "SpiderNix - Enterprise web crawler for public data collection";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
    owasaka = {
      url = "git+file:///home/kernelcore/master/owasaka";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      owasaka,
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

        owasaka-pkg = owasaka.packages.${system}.default;

      in
      {
        # ── devShells ──────────────────────────────────────────────────────────

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

            cat <<EOF

   _____       _     _           _   __ _
  / ____|     (_)   | |         | | / /(_)
 | (___  _ __  _  __| | ___ _ __| |/ /  ___  __
  \___ \| '_ \| |/ _` |/ _ \ '__|    \ | \ \/ /
  ____) | |_) | | (_| |  __/ |  | |\  \| |>  <
 |_____/| .__/|_|\__,_|\___|_|  |_| \_\_/_/\_\
        | |
        |_|   Dev Shell

Python  : $(python --version)
Just    : $(just --version)
uv      : $(uv --version)
Helper  : sp -> spider

Core Commands
  spider crawl <url>       Crawl a target
  spider recon --help      Explore recon modules
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
          '';
        };

        # Full stack: spider-nix + owasaka SIEM + browser + NATS
        devShells.full = pkgs.mkShell {
          name = "spider-nix-full";

          buildInputs = with pkgs; [
            pythonEnv
            playwright-driver.browsers
            nodejs_24
            just
            playwright
            hyperfine
            spiderCli
            uv
            pre-commit
            git
            go
            gopls

            # owasaka stack
            owasaka-pkg
            libpcap
            firefox-esr
            nats-server
            natscli
          ];

          shellHook = ''
            export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
            export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
            export PYTHONPATH="$PWD/src:$PYTHONPATH"

            # owasaka integration env vars
            export SPIDER_OWASAKA_URL="http://localhost:8080"
            export SPIDER_OWASAKA_PROXY="http://localhost:8888"
            export SPIDER_OWASAKA_WS="ws://localhost:8080/ws"
            export SPIDER_NATS_URL="nats://localhost:4222"

            sp() { spider "$@"; }

            owasaka-start() {
              local cfg="''${1:-${../owasaka/configs/examples/default.yaml}}"
              echo "[owasaka] starting with config: $cfg"
              oswaka -config "$cfg" &
              export OWASAKA_PID=$!
              echo "[owasaka] PID $OWASAKA_PID — API at $SPIDER_OWASAKA_URL"
            }

            owasaka-stop() {
              if [ -n "''${OWASAKA_PID:-}" ]; then
                kill "$OWASAKA_PID" 2>/dev/null && echo "[owasaka] stopped"
                unset OWASAKA_PID
              fi
            }

            echo ""
            echo "  spider-nix [full stack]"
            echo "  owasaka : $(oswaka -version 2>/dev/null || echo 'ready')"
            echo "  spider  : available"
            echo ""
            echo "  Commands:"
            echo "    owasaka-start          Start owasaka SIEM (background)"
            echo "    owasaka-stop           Stop owasaka"
            echo "    spider job-hunt        Start job hunt agent"
            echo ""
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
    ) // {

    # ── NixOS Module ───────────────────────────────────────────────────────────
    # Usage:
    #   imports = [ spider-nix.nixosModules.default owasaka.nixosModules.default ];
    #   services.spider-nix = { enable = true; profileFile = /etc/spider-nix/profile.toml; };
    #   services.owasaka = { enable = true; configFile = /etc/owasaka/config.yaml; };
    nixosModules.default =
      { config
      , lib
      , pkgs
      , ...
      }:
      let
        cfg = config.services.spider-nix;
      in
      {
        options.services.spider-nix = {
          enable = lib.mkEnableOption "spider-nix job hunt daemon";

          package = lib.mkOption {
            type = lib.types.package;
            default = self.packages.${pkgs.system}.default;
            description = "The spider-nix package to use.";
          };

          profileFile = lib.mkOption {
            type = lib.types.path;
            description = "Path to profile.toml (contains personal data — keep outside Nix store).";
          };

          owasaka = {
            enable = lib.mkOption {
              type = lib.types.bool;
              default = false;
              description = "Connect to a running owasaka SIEM instance.";
            };
            url = lib.mkOption {
              type = lib.types.str;
              default = "http://localhost:8080";
            };
            proxyUrl = lib.mkOption {
              type = lib.types.str;
              default = "http://localhost:8888";
            };
          };

          user = lib.mkOption { type = lib.types.str; default = "spider-nix"; };
          group = lib.mkOption { type = lib.types.str; default = "spider-nix"; };
        };

        config = lib.mkIf cfg.enable {
          users.users.${cfg.user} = {
            isSystemUser = true;
            group = cfg.group;
            description = "spider-nix job hunt daemon";
            home = "/var/lib/spider-nix";
          };
          users.groups.${cfg.group} = { };

          systemd.services.spider-nix = {
            description = "spider-nix job hunt agent";
            after = [ "network-online.target" ]
              ++ lib.optionals cfg.owasaka.enable [ "owasaka.service" ];
            wants = [ "network-online.target" ]
              ++ lib.optionals cfg.owasaka.enable [ "owasaka.service" ];
            wantedBy = [ "multi-user.target" ];

            environment = {
              SPIDER_PROFILE = cfg.profileFile;
            } // lib.optionalAttrs cfg.owasaka.enable {
              SPIDER_OWASAKA_URL = cfg.owasaka.url;
              SPIDER_OWASAKA_PROXY = cfg.owasaka.proxyUrl;
            };

            serviceConfig = {
              Type = "simple";
              User = cfg.user;
              Group = cfg.group;
              ExecStart = "${cfg.package}/bin/spider job-hunt";
              Restart = "on-failure";
              RestartSec = "30s";
              StateDirectory = "spider-nix";
              LogsDirectory = "spider-nix";
              NoNewPrivileges = true;
              ProtectSystem = "strict";
              ProtectHome = true;
              PrivateTmp = true;
            };
          };
        };
      };
  };
}
