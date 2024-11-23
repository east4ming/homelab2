# README

## netboot.xyz ubuntu 24.04.1 autoinstall

> 📚️ References:
>
> - [netboot.xyz docker image](https://github.com/netbootxyz/docker-netbootxyz)
> - [custom.ipxe - netboot.xyz-custom](https://github.com/netbootxyz/netboot.xyz-custom)

1. Use the netboot.xyz docker image
2. Start PXE Server(netboot.xyz) from docker compose. Compared to the upstream, the following changes have been made:
    1. Modify `docker-compose.yml` to enable `NET_ADMIN` and `host` network_mode to expose the dhcp port
    2. Modify `supervisor.conf` and mount it to modify the dhsmasq startup command
    3. Create and mount `dnsmasq.conf` to use the details of dhcp configuration
    4. TODO: Create and mount `custom.ipxe` to autoinstall
    5. Modify and mount `boot.cfg` to modify `live_endpoint` configuration
    6. Modify and mount `ubuntu.ipxe` to change the ubuntu iso download address
    7. Mount `/assets` for ubuntu initrd and vmlinuz
    8. Mount ubuntu server live iso
    9. Mount the ubuntu cloud-init directory, which must have `user-data`(in cloud-init yaml format) and `meta-data` (empty) files
3. cloud init configuration. v1. See the `user-data.j2`.
    1. Pay particular attention to the storage configuration

### Stag Env

2 win 11 hyper-v vm:

1. gen2 - UEFI
2. netboot
3. Switch: external
4. Disable secure boot
5. Set static mac

> 🐾**Notice**:
>
> Currently netboot.xyz needs to be manually selected on each machine after booting to install the corresponding OS.
> You need to manually enter the ubuntu 24.04 netboot install menu, and input the cloud-init config url,
> like this: <http://yourip/init-config/00:15:5d:02:20:2f/>

## Ubuntu Cloud-init

> 📚️ References:
>
> - [subiquity autoinstall schema](https://canonical-subiquity.readthedocs-hosted.com/en/latest/reference/autoinstall-schema.html)
> - [cloud-init](https://cloudinit.readthedocs.io/en/latest/)]
>
> I use the **subiquity autoinstall**

Compared to the upstream, the following changes have been made:

- User change:
  - Use normal user instead of root
  - Normal user add password
  - Change to zsh
- Package change:
  - Package upgrade
  - More utilities
- Install Tailscale
- Install Starship
