# RoadMap

## Optimized for China

- [ ] YUM Repo
- [ ] Docker Registry
- [ ] NTP Server
- [ ] Add domains to `/etc/hosts` and coredns configmap

## Change OS To Ubuntu 24.04

- [ ] pxe
- [ ] dnf
- [ ] sysctl
- [ ] automatic
- [ ] kured: `rebootSentinelCommand`

## Non-PXE Install

## K3s

- [ ] kubevip/control_plane_endpoint change
- [ ] Version
- [ ] prerequisites
- [ ] k3s config
    - [ ] more tls-sans
    - [ ] disable cloud provider
- [ ] tailscale?
- [ ] `embedded-registry: true`

## System

- [ ] cert-manager/ingress-nginx -> traefik

## VPN

- [ ] Tailscale

## Observability

### Logs

- [x] Add journald logs

### Metrics

- [ ] PV
- [ ] More Alerts
- [ ] More ServiceMonitor
- [ ] More PrometheusRules

### Grafana

- [ ] More Dashboards
- [x] PV
- [x] grafana-sso default role to `admin`

## Security

- [ ] Fail2Ban
- [ ] Disable root login

## My Apps

## 🐛Bug Fix

- [ ] Increase the timeout seconds of `Wait for the machines to come online`
- [ ] Fix PXE HTTP Server 403 - `user: root`
- [ ] Grafana query loki error
    - [ ] `too many outstanding requests`
    - [ ] `parse error at line 1, col 71: syntax error: unexpected IDENTIFIER`

## Homelab Blog

## NIX Packages

- [ ] ping
- [ ] nslookup
- [ ] starship

## Makefile to GoTask
