# Contributing

## How to contribute

### Commits and versions

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org):

```
<type>(<scope>): <subject>
```

- Allowed types: `feat` `fix` `docs` `chore` `refactor` `perf` `build` `test` `ci` `revert`.
- The subject may be written in Chinese.
- Do not use `[Spec Kit] ...` prefixes, bare `update` / `fixed` subjects, or a plain paragraph as the subject line.

Version tags, branches and releases are described in [versioning](versioning.md).

### Bug report

You can [create a new GitHub issue](https://github.com/east4ming/homelab2/issues/new/choose) with the bug report template.

### Submitting patches

Because you may have a lot of changes in your fork, you can't create a pull request directly from your `master` branch.
Instead, create a branch from the upstream repository and commit your changes there:

```sh
git remote add upstream https://github.com/east4ming/homelab2
git fetch upstream
git checkout upstream/master
git checkout -b contrib-fix-something

# Make your changes here
#
# nvim README.md
# git cherry-pick a1b2c3
#
# commit, push, etc. as usual
```

Then you can send the patch using [GitHub pull request](https://github.com/east4ming/homelab2/pulls) or `git send-email` to <cuikaidong@foxmail.com>.
