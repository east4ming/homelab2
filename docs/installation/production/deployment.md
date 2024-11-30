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

So, add the following static routes to your router:

```sh
route add -net 10.42.0.0 netmask 255.255.255.0 gw <pod cidr is the k8s node internal ip address for 10.42.0.0> dev <router-lan-interface>
route add -net 10.42.1.0 netmask 255.255.255.0 gw <pod cidr is the k8s node internal ip address for 10.42.1.0> dev <router-lan-interface>
route add -net 10.42.2.0 netmask 255.255.255.0 gw <pod cidr is the k8s node internal ip address for 10.42.1.0> dev <router-lan-interface>
route add -net 10.42.3.0 netmask 255.255.255.0 gw <pod cidr is the k8s node internal ip address for 10.42.1.0> dev <router-lan-interface>
```

Alternatively, it can be configured through the router UI, as shown in the following example.

![Route UI Add Static Routes](https://github.com/user-attachments/assets/e2e20ad7-154d-42db-badd-070779e05c84)

> 🐾**Warning**:
>
> The above commands are for reference only, you may need to configure them in the UI interface on your router, or the commands may be completely different.
