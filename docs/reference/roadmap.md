# Roadmap

!!! info

    Current status: **ALPHA**

## East4Ming/Homelab2 Roadmap

### Optimized for China

- [ ] YUM/APT Repo
- [ ] Docker Registry
- [x] NTP Server
- [ ] Add domains to `/etc/hosts` and coredns configmap

### Change OS To Ubuntu 24.04

- [x] pxe - use netboot.xyz
- [x] cloud-init - use **subiquity autoinstall**
- [x] dnf
- [x] sysctl
- [x] automatic
- [x] kured: `rebootSentinelCommand`

### Non-PXE Install

### K3s

- [x] Version
- [x] prerequisites
- [ ] k3s config
  - [ ] more tls-sans
  - [x] disable cloud provider
- [x] tailscale
- [x] `embedded-registry: true`

### Cilium Tuning

- [x] update cilium version
- [x] enable native routing mode
- [x] bpf masquerade
- [x] enable DSR
- [x] Bypass iptables connection tracking
- [x] bandwidthManager
- [x] pod BBR
- [x] enable XDPAcceleration
- [x] envoy DaemonSet (cilium 1.16 default)
- [x] hubble grafana dashboards
- [x] netkit

### System

#### Add Tailscale Operator

- [ ] external terraform tailscale
  - [ ] ACL
  - [ ] OAuth
- [x] tailscale operator helm
- [x] tailscale ingress - replace nginx ingress
- [x] tailscale k8s api server
- [x] tailscale cert - replace cert-manager
- [x] tailscale funnel - replace cloudflared
- [x] tailscale dns - replace external-dns
- [x] tailscale proxygroup

### Observability

#### Logs

- [x] Add journald logs

#### Metrics

- [x] PV
- [x] More ServiceMonitor
  - [x] Cilium
  - [x] Volsync
  - [x] K3s kubeControllerManager/kubeScheduler/kubeEtcd and disable kube-proxy(because not used)
  - [x] ArgoCD
  - [x] Kured
  - [x] Loki/Promtail
  - [x] Rook Ceph CSI
  - [x] Gitea
  - [x] Woodpecker(PodMonitor)
  - [x] Dex
  - [x] external-secrets
  - [x] Grafana
  - [x] Zot
- [ ] More PrometheusRules/Alerts
  - [x] ArgoCD
  - [x] Loki/Promtail
  - [x] Woodpecker

#### Grafana

- [ ] More Dashboards
  - [x] Cilium
  - [x] Woodpecker
- [x] PV

### Security

- [ ] Fail2Ban
- [x] Disable root login

### My Apps

### 🐛Bug Fix

- [x] Increase the timeout seconds of `Wait for the machines to come online`
- [ ] Grafana query loki error
  - [ ] `too many outstanding requests`
  - [ ] `parse error at line 1, col 71: syntax error: unexpected IDENTIFIER`

### Homelab Blog

### NIX Packages

- [ ] ping
- [ ] nslookup
- [x] starship(but throuth autoinstall runcmd)
- [ ] krew

### Makefile to GoTask

### Public Repo

- [ ] Modify TODO:
- [ ] Remove hard codes
- [x] Remove secrets
- [x] Add more docs
- [ ] Add more examples
- [ ] Add more templates
- [ ] Modify code/configuration/documentation related to the git repo

## Alpha requirements

Literally anything that works.

## Beta requirements

Good enough for tinkering and personal usage, and reasonably secure.

- [x] Automated bare metal provisioning
  - [x] Controller set up (Docker)
  - [x] OS installation (PXE boot)
- [x] Automated cluster creation (k3s)
- [x] Automated application deployment (ArgoCD)
- [x] Automated DNS management
- [x] Initialize GitOps repository on Gitea automatically
- [x] Observability
  - [x] Monitoring
  - [x] Logging
  - [x] Alerting
- [x] SSO
- [ ] Reasonably secure
  - [x] Automated certificate management
  - [x] Declarative secret management
  - [ ] Replace all default passwords with randomly generated ones
  - [x] Expose services to the internet securely with Cloudflare Tunnel
- [x] Only use open-source technologies (except external managed services in `./external`)
- [x] Everything is defined as code
- [ ] Backup solution (3 copies, 2 seperate devices, 1 offsite)
- [ ] Define [SLOs](https://en.wikipedia.org/wiki/Service-level_objective):
  - [ ] 70% availability (might break in the weekend due to new experimentation)
- [x] Core applications
  - [x] Gitea
  - [x] Woodpecker
  - [x] Private container registry
  - [x] Homepage

## Stable requirements

Can be used in "production" (for family or even small scale businesses).

- [x] A single command to deploy everything
- [x] Fast deployment time (from empty hard drive to running services in under 1 hour)
- [ ] Fully _automatic_, not just _automated_
  - [x] Bare-metal OS rolling upgrade
  - [x] Kubernetes version rolling upgrade
  - [x] Application version upgrade
  - [ ] Encrypted backups
  - [ ] Secrets rotation
  - [x] Self healing
- [ ] Secure by default
  - [ ] SELinux
  - [ ] Network policies
- [ ] Static code analysis
- [ ] Chaos testing
- [x] Minimal dependency on external services
- [ ] Complete documentation
  - [x] Diagram as code
  - [x] Book (this book)
  - [ ] Walkthrough tutorial and feature demo (video)
- [x] Configuration script for new users
- [ ] More dashboards and alert rules
- [ ] SLOs:
  - [ ] 99,9% availability (less than 9 hours of downtime per year)
  - [ ] 99,99% data durability
- [ ] Clear upgrade path
- [ ] Additional applications
  - [ ] Matrix with bridges
  - [ ] VPN server
  - [ ] PeerTube
  - [x] Blog
  - [ ] [Development dashboard](https://github.com/khuedoan/homelab-backstage)

## Unplanned

Nice to have

- [ ] Addition applications
  - [ ] Mail server
- [ ] Air-gap install
- [ ] Automated testing
- [ ] Security audit
- [ ] Serverless ([Knative](https://knative.dev))
- [ ] Cluster API ([last attempt](https://github.com/khuedoan/homelab/pull/2))
- [ ] Split DNS (requires a better router)
