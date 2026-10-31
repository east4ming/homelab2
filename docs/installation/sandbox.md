# Development sandbox

The sandbox is intended for trying out the homelab without any hardware or testing changes before applying them to the production environment.

## Prerequisites

Host machine:

- Recommended hardware specifications:
  - CPU: 6 cores
  - RAM: 64 GiB
- OS: Windows 10 or 11
- Available ports: `80` and `443`

> 🤔**Thinking**:
>
> In order to better simulate the `metal` part of the content, I finally decided to use virtual machines instead of k3d as a sandbox.

The sandbox uses Windows as the host, with 1 operational VM + 2 sandbox VMs. Windows requires Hyper-V to be installed.

## Hyper-V Creating Virtual Machines

### Create an internal-only virtual switch

> 📚️**Reference**:
>
> [Hyper-V Custom Internal Network Segments and IP Addresses](https://zahui.fan/posts/6f952944/)

Open PowerShell as Administrator and run the following command:

```powershell
# Creating a virtual switch is equivalent to creating a new virtual network switch in the Hyper-V Manager interface
New-VMSwitch -SwitchName "NAT" -SwitchType Internal

# Get the ifindex of the virtual switch and assign it to the variable
$ifindex = Get-NetAdapter -Name "vEthernet (NAT)" | Select-Object -ExpandProperty 'ifIndex'
# Setting a fixed IP on the virtual switch for gateway IPs
New-NetIPAddress -IPAddress 192.168.200.1 -PrefixLength 24 -InterfaceIndex $ifindex

# 192.168.200.1 which is the gateway address
New-NetNat -Name NAT -InternalIPInterfaceAddressPrefix 192.168.200.1/24
```

### Creating Virtual Machines

Create 3 new VM with the following settings:

**homelab-dev-bastion**

- Name: `homelab-dev-bastion`
- Memory: 4 GiB
- Processors: 4
- Disk size: 50 GiB
- Network: `NAT`
- OS: `Ubuntu 26.04.1`
- Installation type: `ISO`

**homelab-dev-master**

- Name: `homelab-dev-master`
- Memory: 16 GiB
- Processors: 4
- Disk size: 128 GiB
- Network: `NAT`
- OS: later
- boot from: network

**homelab-dev-node**

- Name: `homelab-dev-node`
- Memory: 16 GiB
- Processors: 4
- Disk size: 128 GiB
- Network: `NAT`
- OS: later
- boot from: network

For the homelab-dev-bastion, install the following packages:

- `docker`
- `mise` and `uv` (see [development environment](../concepts/development-shell.md) for setup)

Clone the repository and checkout the development branch:

```sh
git clone https://github.com/east4ming/homelab2
#TODO: dev branch
git checkout dev
```

## Build

Prepare the development environment, which includes all the tools needed:

```sh
mise run setup
```

Build a development cluster and bootstrap it:

```
make
```

Then boot `homelab-dev-master` and `homelab-dev-node`, to start the netboot.xyz installation.

Finally, since Cilium enables the native routing feature, you need to configure static routes on your router (in a Hyper-V VM scenario, that is, the Windows host). The pod CIDR of a node is assigned dynamically by `kube-controller-manager`, so read the mapping from the cluster instead of hardcoding it (see [Add Router Static Routes](production/deployment.md#add-router-static-routes)):

```sh
kubectl get nodes -o custom-columns=NAME:.metadata.name,PODCIDR:.spec.podCIDR
```

Every line of that output is one route, sending the pod CIDR to the internal IP address of that same node:

```cmd
route ADD <pod cidr> MASK 255.255.255.0  <node internal ip address>
```

Re-run the command and fix the routes whenever you add or rebuild a node, otherwise cross-node pod traffic breaks silently.

!!! note

    It will take about 15 to 30 minutes to build depending on your internet connection

## Explore

The homepage should be available at `https://homelab-dev-home.<your-fun-tailnet-name>.ts.net`.

See [admin credentials](post-installation.md#admin-credentials) for default passwords.

If you want to make some changes, simply commit to the local `dev` branch and push it to Gitea in the sandbox:

```sh
git remote add sandbox https://homelab-dev-git.127-0-0-1.<your-fun-tailnet-name>.ts.net/ops/homelab

git add foobar.txt
git commit -m "feat: harness the power of the sun"
git push sandbox # you can use the gitea_admin account
```

## Clean up

Delete the cluster:

1. Delete Terraform Cloud resources
2. Delete Tailscale machines
   1. `tags: dev-k8s`
   2. `tags: dev-k8s-operator`
3. delete 3 hyper-v virtual machines
4. delete `NAT` hyper-v virtual switch

## Caveats compare to production environment

The development cluster doesn't have the following features:

- No backup

Please keep in mind that the development cluster may be unstable and things may break (it's for development after all).
