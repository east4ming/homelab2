# Security policy

## Scope

This repository holds the desired state of a private homelab cluster: Ansible
roles, Helm values and manifests. It is a state repository, not a library —
`master` is deployed continuously by ArgoCD, so anything merged here reaches the
cluster.

Secret **values** are not committed. They live in `external/terraform.tfvars`
(ignored via `external/.gitignore`) and are synced into the cluster by the
[External Secrets Operator](docs/concepts/secrets-management.md). The tracked
`secret*.yaml` files only describe how a secret is assembled; they contain no
credentials.

## Reporting a vulnerability

Please report privately instead of opening a public issue:

- Email: <cuikaidong@foxmail.com>

Include what is affected (file, service or cluster component), how to reproduce
it, and the impact you see. This is a personal homelab maintained by one person:
reports are handled on a best-effort basis, there is no SLA and no bug bounty.

## Supported versions

Only `master` is supported: it is the branch ArgoCD deploys. Fixes are merged
there and tagged as rollback points; published tags are never moved or deleted.
See [versioning](docs/reference/versioning.md).
