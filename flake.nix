{
  description = "Homelab";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-26.05";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      with pkgs;
      {
        devShells.default = mkShell {
          packages = [
            ansible
            ansible-lint
            argocd
            bmake
            diffutils
            docker
            docker-compose
            dyff
            git
            glibcLocales
            go
            gotestsum
            iproute2
            jq
            k9s
            kanidm_1_11 # deployed server is 1.3.3 (platform/kanidm); nixpkgs 26.05 dropped <= 1.6
            k3d
            kubectl
            kubernetes-helm
            kustomize
            libisoburn
            neovim
            openssh_gssapi
            opentofu # Drop-in replacement for Terraform
            p7zip
            pre-commit
            qrencode
            shellcheck
            wireguard-tools
            yamllint

            (python3.withPackages (p: with p; [
              jinja2
              kubernetes
              mkdocs-material
              netaddr
              pexpect
              rich
            ]))
          ];
        };

        # Minimal shell for CI static checks (.woodpecker/static-checks.yaml):
        # only the binaries the pre-commit hooks shell out to. Deliberately not
        # the default devShell, which pulls in docker/k9s/neovim and costs
        # several GB to download on every pipeline run.
        devShells.ci = mkShell {
          packages = [
            git
            kubernetes-helm # helmlint
            opentofu # tofu_fmt
            pre-commit
            shellcheck # shellcheck hook
            yamllint # yamllint hook
          ];
        };
      }
    );
}
