{
  description = "Spider-Nix Network Proxy - uTLS-based anti-detection proxy";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        packages.default = pkgs.buildGoModule {
          pname = "spider-network-proxy";
          version = "0.1.0";

          src = ./.;

          vendorHash = null;  # Will need to be set after go mod vendor

          meta = with pkgs.lib; {
            description = "Anti-detection HTTP/HTTPS proxy with TLS fingerprinting";
            license = licenses.mit;
            platforms = platforms.linux;
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            go
            gopls
            gotools
            go-tools
          ];

          shellHook = ''
            echo "🕸️  Spider-Nix Network Proxy"
            echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            echo "Go: $(go version)"
            echo ""
            echo "Commands:"
            echo "  go run ./cmd/spider-network-proxy       Run proxy"
            echo "  go build ./cmd/spider-network-proxy     Build binary"
            echo "  go test ./...                           Run tests"
          '';
        };
      }
    );
}
