# Contributing

The full guide lives in the documentation: [Contributing](docs/reference/contributing.md).

Before you open a pull request:

- **Never commit to `master`.** It is deployed by ArgoCD (`automated` +
  `selfHeal`), so a merge goes live. Work on a branch and open a pull request.
- **Commit messages** follow [Conventional Commits](https://www.conventionalcommits.org):
  `<type>(<scope>): <subject>`, with `type` from `feat` `fix` `docs` `chore`
  `refactor` `perf` `build` `test` `ci` `revert`. The subject may be written in
  Chinese, the project language.
- **Versions and releases** are date tags (`vYYYY.MM.DD[.N]`) described in
  [versioning](docs/reference/versioning.md); a published tag is never moved or
  deleted.
- **Hooks and checks**: `make git-hooks` installs the pre-commit hooks
  (yamllint, shellcheck, `tofu fmt`, whitespace and private-key checks). The same
  pre-commit run happens in CI. Documentation changes must pass
  `mkdocs build --strict`, which fails on broken links.
