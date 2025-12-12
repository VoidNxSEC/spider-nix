{
  description = "SpiderNix - Enterprise web crawler for public data collection";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        
        pythonEnv = pkgs.python311.withPackages (ps: with ps; [
          # Core crawling
          httpx
          aiohttp
          aiosqlite
          pydantic
          
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
        
      in {
        devShells.default = pkgs.mkShell {
          name = "spider-nix-dev";
          
          buildInputs = with pkgs; [
            pythonEnv
            playwright-driver.browsers
            nodePackages.npm
          ];
          
          shellHook = ''
            export PLAYWRIGHT_BROWSERS_PATH="${pkgs.playwright-driver.browsers}"
            export PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1
            
            echo "🕷️  SpiderNix Development Environment"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "Python: $(python --version)"
            echo ""
            echo "Commands:"
            echo "  pip install -e .        Install spider-nix"
            echo "  pytest tests/           Run tests"
            echo "  spider-nix --help       CLI help"
          '';
        };
        
        packages.default = pkgs.python311Packages.buildPythonApplication {
          pname = "spider-nix";
          version = "0.1.0";
          format = "pyproject";
          
          src = ./.;
          
          nativeBuildInputs = with pkgs.python311Packages; [
            hatchling
          ];
          
          propagatedBuildInputs = with pkgs.python311Packages; [
            httpx
            aiohttp
            aiosqlite
            pydantic
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
      });
}
