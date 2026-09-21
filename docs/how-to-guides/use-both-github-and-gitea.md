# Use both GitHub and Gitea

Gitea is the authoritative remote. GitHub is kept as a mirror for discovery and for the Cloudflare Pages build of the documentation site.

## The actual configuration

`origin` in this repository carries **two** `remote.origin.url` values (not `pushurl`):

```sh
git config --get-all remote.origin.url
# https://git.west-beta.ts.net/ops/homelab2.git   <- Gitea, authoritative
# https://github.com/east4ming/homelab2.git       <- GitHub, mirror
```

Git fetches from the **first** URL and pushes to **every** URL, so one `git push` reaches both remotes:

```sh
git push origin master v2026.09.21
```

!!! warning

    Both URLs must be HTTPS. GitHub over SSH does not work on this machine — see below.

To set this up in your own fork, replace both URLs, and make sure the first one is the remote you want to fetch from:

```sh
git remote set-url --add origin https://github.com/<you>/homelab2.git
```

## Verify what actually landed

The exit code of `git push` is not enough (see failure semantics below). Check both sides:

```sh
git ls-remote --tags origin
git ls-remote --tags https://github.com/east4ming/homelab2.git
```

## Failure semantics

If either remote rejects the push, `git push` exits **128** — but the other remote may already have been updated:

```
To https://git.west-beta.ts.net/ops/homelab2.git
 * [new tag]         v2026.09.21 -> v2026.09.21     # Gitea: succeeded
Bad owner or permissions on /etc/ssh/ssh_config.d/...
fatal: Could not read from remote repository.       # GitHub: failed
```

Never read exit code 128 as "nothing was pushed". Fix the failing side, then push again — re-pushing an already-updated remote is a no-op.

## GitHub push fails: `Could not read from remote repository`

First find out whether SSH works at all:

```sh
ssh -G github.com; echo $?
```

`255` means SSH itself is broken, not the GitHub credentials. On this machine every SSH invocation fails with:

```
Bad owner or permissions on /etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf
```

The cause is a dangling symlink owned by `nobody:nogroup`:

```
/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf
  -> /usr/lib/systemd/ssh_config.d/20-systemd-ssh-proxy.conf
```

`/etc/ssh/ssh_config` includes `/etc/ssh/ssh_config.d/*.conf`, OpenSSH refuses the file because of its owner, and aborts reading the configuration. Fixing it needs root; it is left alone here because the Git remotes only ever use HTTPS.

## Switch the GitHub push URL from SSH to HTTPS

```sh
git remote set-url --delete origin git@github.com:east4ming/homelab2.git
git remote set-url --add    origin https://github.com/east4ming/homelab2.git
```

Then verify — `--dry-run` writes nothing:

```sh
git push --dry-run https://github.com/east4ming/homelab2.git master
```

If that fails on credentials, point git at the authenticated `gh` CLI (`gh auth status` should show an account with the `repo` scope):

```sh
gh auth setup-git
```
