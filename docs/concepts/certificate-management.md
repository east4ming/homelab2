# Certificate management

Certificates are generated and managed by [Tailscale HTTPS](https://tailscale.com/kb/1153/enabling-https) with [Let's Encrypt](https://letsencrypt.org).

- To enable HTTPS for Tailscale, you need a TLS certificate from a public Certificate Authority (CA), which can be obtained through the Tailscale admin console.
- To provision TLS certificates for devices in your tailnet, you need to enable MagicDNS and HTTPS Certificates in the admin console, then run tailscale cert on each machine to obtain a certificate.
- TLS certificates are issued based on your tailnet name and are recorded in the Certificate Transparency (CT) public ledger, which includes the fully qualified domain name of your devices.
- Certificates provided by Let's Encrypt have a 90-day expiry and require periodic renewal, which can be done automatically or manually depending on the integration used.
- You can disable HTTPS for your tailnet, but this will break all links and connections that relied on HTTPS, and certificates will not be revoked.

## [ Exposing cluster workloads using a Kubernetes `Ingress`](https://tailscale.com/kb/1439/kubernetes-operator-cluster-ingress#exposing-cluster-workloads-using-a-kubernetes-ingress)

You can expose cluster workloads either to your tailnet or the public internet over TLS using an`Ingress` resource. When using an `Ingress` resource, you also get the ability to identify callers using [HTTP headers](https://tailscale.com/kb/1312/serve#identity-headers) injected by the `Ingress` proxy.

`Ingress` resources only support TLS, and are only exposed over HTTPS using a [MagicDNS](https://tailscale.com/kb/1081/magicdns) name and publicly trusted certificates from LetsEncrypt. You must [enable HTTPS](https://tailscale.com/kb/1153/enabling-https) and [MagicDNS](https://tailscale.com/kb/1081/magicdns) on your tailnet.

Edit the `Ingress` resource you want to expose to use the `Ingress` class `tailscale`:

1. Set `spec.ingressClassName` to `tailscale`.
2. Set `tls.hosts` to the desired host name of the Tailscale node. Only the first label is used. See [custom machine names](https://tailscale.com/kb/1445/kubernetes-operator-customization#custom-machine-names) for more details.

For example, to expose an `Ingress` resource `nginx` to your tailnet:

```yaml hl_lines="11 14"
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: foo
spec:
  defaultBackend:
    service:
      name: foo
      port:
        number: 80
  ingressClassName: tailscale
  tls:
    - hosts:
        - foo
```

Currently the only supported [`Ingress` path type](https://kubernetes.io/docs/concepts/services-networking/ingress/#path-types) is `Prefix`. Requests for paths with other path types will be routed according to `Prefix` rules.

A Tailscale `Ingress` can **only** be accessed on port 443.

A much more detailed diagram can be found in the official documentation under:

- [Enabling HTTPS · Tailscale Docs](https://tailscale.com/kb/1153/enabling-https)
- [Kubernetes operator · Tailscale Docs](https://tailscale.com/kb/1439/kubernetes-operator-cluster-ingress)
