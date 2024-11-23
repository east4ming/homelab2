# RoadMap

## Optimized for China

- [ ] YUM/APT Repo
- [ ] Docker Registry
- [ ] NTP Server
- [ ] Add domains to `/etc/hosts` and coredns configmap

## Change OS To Ubuntu 24.04

- [x] pxe - use netboot.xyz
- [x] cloud-init - use **subiquity autoinstall**
- [x] dnf
- [x] sysctl
- [x] automatic
- [x] kured: `rebootSentinelCommand`

## Non-PXE Install

## K3s

- [x] Version
- [x] prerequisites
- [ ] k3s config
    - [ ] more tls-sans
    - [x] disable cloud provider
- [x] tailscale
- [x] `embedded-registry: true`

## Cilium Tuning

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

## System

### Add Tailscale Operator

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

## Observability

### Logs

- [x] Add journald logs

### Metrics

- [x] PV
- [ ] More Alerts
- [ ] More ServiceMonitor
  - [x] Cilium
- [ ] More PrometheusRules

### Grafana

- [ ] More Dashboards
  - [x] Cilium
- [x] PV
- [x] grafana-sso default role to `admin`

## Security

- [ ] Fail2Ban
- [x] Disable root login

## My Apps

## 🐛Bug Fix

- [x] Increase the timeout seconds of `Wait for the machines to come online`
- [ ] Grafana query loki error
    - [ ] `too many outstanding requests`
    - [ ] `parse error at line 1, col 71: syntax error: unexpected IDENTIFIER`

## Homelab Blog

## NIX Packages

- [ ] ping
- [ ] nslookup
- [ ] starship
- [ ] krew

## Makefile to GoTask

## Public Repo

- [ ] Modify TODO:
- [ ] Remove hard codes
- [ ] Remove secrets
- [ ] Add more docs
- [ ] Add more examples
- [ ] Add more templates
- [ ] Modify code/configuration/documentation related to the git repo
