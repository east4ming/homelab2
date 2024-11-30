# Networking

```mermaid
flowchart TD

  laptop/desktop/phone <-- Tailscale VPN Over Internet/Intranet --> Tailscale Ingress Pod

  subgraph LAN
    subgraph k8s[Kubernetes cluster]
      Pod --> Service
      Service --> Ingress

      Tailscale Ingress Pod

      Tailscale Funnel Ingress Pod
      Tailscale Funnel Ingress Pod <--> Ingress
    end
    Tailscale Ingress Pod <--> Ingress
  end

  Tailscale Funnel Ingress Pod -- outbound --> ts.net
  Internet -- inbound --> ts.net
```

TODO (PR welcomed)
