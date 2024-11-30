# Prerequisites

## Fork this repository

Because [this project](https://github.com/east4ming/homelab2) applies GitOps practices,
it's the source of truth for _my_ homelab, so you'll need to fork it to make it yours:

[:fontawesome-solid-code-fork: Fork east4ming/homelab2](https://github.com/east4ming/homelab2/fork){ .md-button }

By using this project you agree to [the license](../../reference/license.md).

!!! summary "License TL;DR"

     - This project is free to use for any purpose, but it comes with no warranty
     - You must use the same [GPLv3 license](https://www.gnu.org/licenses/gpl-3.0.en.html)  in `LICENSE.md`
     - You must keep the copy right notice and/or include an acknowledgement
     - Your project must remain open-source

## Hardware requirements

### Router HardWare

Router that support configuration of static routes, because Cilium is performance tuned to use native routing feature, this requires a router that supports static routing. (Of course, you can also modify Cilium's configuration to not use native routing feature.)

(Optional) It would be better if the router supports DHCP/DNS -> PXE/TFTP function, which can easily work with netboot.xyz for PXE based on dhcp proxy. Like below:

![OpenWrt -> DHCP/DNS -> PXE/TFTP](TODO:)

### Initial controller

!!! info

    The initial controller is the machine used to bootstrap the cluster, we only need it once, you can use your laptop or desktop

- A **Linux** machine that can run Docker (because the `host` networking driver used for PXE boot [only supports Linux](https://docs.docker.com/network/host/), you can use a Linux virtual machine with bridged networking if you're on macOS or Windows).

### Servers

Any modern `x86_64` computer(s) should work, you can use old PCs, laptops or servers.

!!! info

    This is the requirements for _each_ node

| Component  | Minimum                                                                                                             | Recommended                                                                                  |
| :--------- | :------------------------------------------------------------------------------------------------------------------ | :------------------------------------------------------------------------------------------- |
| CPU        | 2 cores                                                                                                             | 4 cores                                                                                      |
| RAM        | 8 GB                                                                                                                | 16 GB                                                                                        |
| Hard drive | 128 GB                                                                                                              | 512 GB (depending on your storage usage, the base installation will not use more than 128GB) |
| Node count | 1 (checkout the [single node cluster adjustments](../../how-to-guides/single-node-cluster-adjustments.md) tutorial) | 3 or more for high availability                                                              |

Additional capabilities:

- Ability to boot from the network (PXE boot)
  - In fact, there are alternatives to a PXE boot, which is to automate the installation using a USB as a boot disk (which is what my Cheshi does), such as using the [Ventoy Autoinstall Plugin](https://www.ventoy.net/en/plugin_autoinstall.html)
- Wake-on-LAN capability, used to wake the machines up automatically without physically touching the power button

### Network setup

- Smooth access to the Internet, including but not limited to: docker.io and GitHub...
- All servers must be connected to the same **wired** network with the initial controller
- You have the access to change DNS config (on your router or at your domain registrar)

#### Router DHCP PXE Proxy Config

For OpenWrt, You can configure the following:

```sh
vi /etc/config/dhcp
```

Add the following:

```ini
config boot
	option filename 'netboot.xyz.efi'
	option servername 'netbootxyz'
	option serveraddress '192.168.3.225
```

> ✍**Notes**:
>
> `192.168.3.225` is the IP address of your initial controller

Then reboot service:

```sh
/etc/init.d/dnsmasq restart
```

## Domain

We use Tailscale [MagicDNS](https://tailscale.com/kb/1217/tailnet-name) directly to provide domains/certificates/tunnel, all you need to do is to enable this, as follows:

- [MagicDNS · Tailscale Docs](https://tailscale.com/kb/1081/magicdns#enabling-magicdns)
- [Tailnet name · Tailscale Docs](https://tailscale.com/kb/1217/tailnet-name#creating-a-fun-tailnet-name)
- [Enabling HTTPS · Tailscale Docs](https://tailscale.com/kb/1153/enabling-https#configure-https)

## BIOS setup

!!! info

    You need to do it once per machine if the default config is not sufficent,
    usually for consumer hardware this can not be automated
    (it requires something like [IPMI](https://en.wikipedia.org/wiki/Intelligent_Platform_Management_Interface) to automate).

Common settings:

- Enable Wake-on-LAN (WoL) and network boot
- Use UEFI mode and disable CSM (legacy) mode
- Disable secure boot

Boot order options (select one, each has their pros and cons):

1. Only boot from the network if no operating system found: works on most hardware but you need to manually wipe your hard drive or delete the existing boot record for the current OS
2. Prefer booting from the network if turned on via WoL: more convenience but your BIOS must support it, and you must test it throughly to ensure you don't accidentally wipe your servers

!!! example

    Below is my BIOS setup for reference. Your motherboard may have a different name for the options, so you'll need to adapt it to your hardware.

    ```yaml
    Devices:
      NetworkSetup:
        PXEIPv4: true
        PXEIPv6: false
    Advanced:
      CPUSetup:
        VT-d: true
    Power:
      AutomaticPowerOn:
        WoL: Automatic  # Use network boot if Wake-on-LAN
    Security:
      SecureBoot: false
    Startup:
      CSM: false
    ```

## Tailscale (requires third-party account)

### For Node

Get an [auth key](https://tailscale.com/kb/1085/auth-keys) from [Tailscale admin console](https://login.tailscale.com/admin/authkeys), which is used for tailscale installation on node:

- Description: homelab
- Reusable: optionally set this to true

You can now connect to your homelab via Tailscale and [invite user to your Tailscale network](https://tailscale.com/kb/1371/invite-users).

### For Kubernetes Operator

> 📚️**Reference**:
>
> [Kubernetes operator · Tailscale Docs](https://tailscale.com/kb/1236/kubernetes-operator#prerequisites)

1. In your [tailnet policy file](https://tailscale.com/kb/1018/acls), create the [tags](https://tailscale.com/kb/1068/tags) `tag:k8s-operator` and `tag:k8s`, and make `tag:k8s-operator` an owner of `tag:k8s`. If you want your `Services` to be exposed with tags other than the default `tag:k8s`, create those as well and make `tag:k8s-operator` an owner.

   ```json
   "tagOwners": {
      "tag:k8s-operator": [],
      "tag:k8s": ["tag:k8s-operator"],
   }
   ```

2. [Create an OAuth client](https://tailscale.com/kb/1215/oauth-clients#setting-up-an-oauth-client) in the [**OAuth clients**](https://login.tailscale.com/admin/settings/oauth) page of the admin console. Create the client with `Devices Core` and `Auth Keys` write scopes, and the tag `tag:k8s-operator`.

## Gather information

- [ ] Decide a `control_plane_endpoint`
- [ ] Adapt the configuration to your situation: `registries_config_yaml`. Minimum configuration is like below. This enables the latest features of k3s: [Embedded Registry Mirror | K3s](https://docs.k3s.io/installation/registry-mirror)
- [ ] MAC address for each machine
- [ ] OS disk name (for example `/dev/sda`)
- [ ] Network interface name (for example `eth0`)
- [ ] Choose a static IP address for each machine (just the desired address, we don't set anything up yet)

```yaml
registries_config_yaml: |
  mirrors:
    "*":
```

△ Minimum configuration for `registries_config_yaml`
