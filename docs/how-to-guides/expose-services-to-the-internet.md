# Expose services to the internet

!!! info

    This tutorial is for Tailscale Funnel users, please skip if you use port forwarding.

Apply the `./external` layer to create a tunnel if you haven't already,
then add the following annotations to your `Ingress` object (replace `example.com` with your domain):

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    tailscale.com/funnel: "true"
# ...
```

## [Exposing a `Service` to the public internet using `Ingress` and Tailscale Funnel](https://tailscale.com/kb/1439/kubernetes-operator-cluster-ingress?q=ingress#exposing-a-service-to-the-public-internet-using-ingress-and-tailscale-funnel)

You can also use the Tailscale Kubernetes operator to expose an `Ingress` resource in your Kubernetes cluster to the public internet using [Tailscale Funnel](https://tailscale.com/kb/1223/funnel). To do so:

1. Add a `tailscale.com/funnel: "true"` annotation:

   ```yaml hl_lines="6"
   apiVersion: networking.k8s.io/v1
   kind: Ingress
   metadata:
     name: bar
     annotations:
       tailscale.com/funnel: "true"
   spec:
     defaultBackend:
       service:
         name: bar
         port:
           number: 80
     ingressClassName: tailscale
     tls:
       - hosts:
           - bar
   ```

2. Update the ACLs for your tailnet to allow Kubernetes Operator proxy services to use Tailscale Funnel.

Add a [node attribute](https://tailscale.com/kb/1223/funnel#requirements-and-limitations) to allow nodes created by the Kubernetes operator to use Funnel:

```hujson
"nodeAttrs": [
  {
    "target": ["tag:k8s"], // tag that Tailscale Operator uses to tag proxies; defaults to 'tag:k8s'
    "attr":   ["funnel"],
  },
  ...
]
```

Note that even if your policy has the `funnel` attribute assigned to `autogroup:member` (the default), you still need to add it to the tag used by proxies because `autogroup:member` does not include tagged devices.
