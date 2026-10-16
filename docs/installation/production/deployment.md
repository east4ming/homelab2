# Deployment

Open the development shell if you haven't already:

```sh
nix develop
```

Or, If your Initial controller Linux distribution is Ubuntu, you need to execute the following command:

```sh
nix develop --extra-experimental-features nix-command --extra-experimental-features flakes
```

Build the lab:

```sh
make
```

Yes it's that simple!

!!! example

    <script id="asciicast-xkBRkwC6e9RAzVuMDXH3nGHp7" src="https://asciinema.org/a/xkBRkwC6e9RAzVuMDXH3nGHp7.js" async></script>

It will take a while to download everything,
you can read the [architecture document](../../reference/architecture/overview.md) while waiting for the deployment to complete.

## Add Router Static Routes

If you haven't modified `metal/roles/cilium/defaults/main.yml`, then your Cilium will enable native routing, as follows:

```yaml
# native routing mode
routingMode: native
autoDirectNodeRoutes: true
ipv4NativeRoutingCIDR: "{{ ipv4_net_mask | ansible.utils.ipaddr('network/prefix') }}"
```

This requires you to manually configure static routes on your router, otherwise pods will not ping other k8s nodes and pods on other k8s nodes.

The pod CIDR of a node is **assigned dynamically by `kube-controller-manager`**: it
is not derived from the node name or from their order, and it can change when a
node is added, removed or reinstalled. So do not copy a CIDR-to-node table from
any document (including this one) into your router. Read the mapping from the
cluster instead:

```sh
kubectl get nodes -o custom-columns=NAME:.metadata.name,PODCIDR:.spec.podCIDR
```

Every line of that output is one static route: send the pod CIDR to the internal
IP address of that same node (the address your router reaches the node on). For
example:

```sh
route add -net <pod cidr> netmask 255.255.255.0 gw <node internal ip> dev <router-lan-interface>
```

!!! warning "Re-check the routes after every node change"

    Adding, removing or reinstalling a node reassigns pod CIDRs. Re-run the
    `kubectl get nodes ...` command above and fix the routes on your router,
    otherwise cross-node pod traffic breaks silently while everything else keeps
    working.

Alternatively, it can be configured through the router UI, as shown in the following example.

![Route UI Add Static Routes](https://github.com/user-attachments/assets/e2e20ad7-154d-42db-badd-070779e05c84)

> 🐾**Warning**:
>
> The above commands are for reference only, you may need to configure them in the UI interface on your router, or the commands may be completely different.
