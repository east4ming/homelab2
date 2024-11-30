# East4Ming's Homelab2

**[Features](#features) • [Get Started](#get-started) • [Documentation](https://homelab2.e-whisper.com)**

[![tag](https://img.shields.io/github/v/tag/east4ming/homelab2?style=flat-square&logo=semver&logoColor=white)](https://github.com/east4ming/homelab2/tags)
[![document](https://img.shields.io/website?label=document&logo=gitbook&logoColor=white&style=flat-square&url=https%3A%2F%2Fhomelab2.e-whisper.com)](https://homelab2.e-whisper.com)
[![license](https://img.shields.io/github/license/east4ming/homelab2?style=flat-square&logo=gnu&logoColor=white)](https://www.gnu.org/licenses/gpl-3.0.html)
[![stars](https://img.shields.io/github/stars/east4ming/homelab2?logo=github&logoColor=white&color=gold&style=flat-square)](https://github.com/east4ming/homelab2)

The project forked from [khuedoan/homelab](https://github.com/khuedoan/homelab), 99% of the credit goes to him. Thanks Khuedoan.

✨**HighLight**:

Compared to the [khuedoan/homelab](https://github.com/khuedoan/homelab) project, the following adjustments have been made to this project:

- 🥾 Automated bare metal provisioning with [netboot.xyz](https://netboot.xyz/)
- 🐧 OS changed to Ubuntu 24.04
- 🕸 Use [Tailscale Operator](https://tailscale.com/kb/1236/kubernetes-operator) replace nginx ingress/cert-manager/cloudflared/external-dns...; Install tailscale on node
- 🐝Cilium Tuning

**Ubuntu**: Kured adapts to ubuntu; The relevant packages are modified to ubuntu's; ubuntu sysctl tuning; automatic adapts to ubuntu; Disable root login and use normal user

**Cilium Tuning**: include: update version/native routing mode/bpf masquerade/DSR/Bypass iptables connection tracking/bandwidthManager/pod BBR/~~XDPAcceleration~~/netkit/servicemonitor/grafana dashboards...(However, the compatibility is relatively lower, and the network/hardware/OS requirements are higher.)

This project utilizes [Infrastructure as Code](https://en.wikipedia.org/wiki/Infrastructure_as_code) and [GitOps](https://www.weave.works/technologies/gitops) to automate provisioning, operating, and updating self-hosted services in my homelab.
It can be used as a highly customizable framework to build your own homelab.

> **What is a homelab?**
>
> Homelab is a laboratory at home where you can self-host, experiment with new technologies, practice for certifications, and so on.
> For more information, please see the [r/homelab introduction](https://www.reddit.com/r/homelab/wiki/introduction) and the
> [Home Operations Discord community](https://discord.gg/home-operations) (formerly known as [k8s-at-home](https://k8s-at-home.com)).

## Overview

Project status: **ALPHA**

This project is still in the experimental stage, and I don't use anything critical on it.
Expect breaking changes that may require a complete redeployment.
A proper upgrade path is planned for the stable release.
More information can be found in [the roadmap](#roadmap) below.

### Hardware

![Hardware](https://github.com/user-attachments/assets/e48caa3e-00c6-460f-87e9-71814faa9888)

- 4 × Intel N100 Mini-hosts(3 x Jumper N100 Pro II + 1 x Cheshi N100):
  - CPU: `Intel(R) N100`
  - RAM: `16GB`(Jumper) or `32GB`(Cheshi)
  - SSD: `1TB`
- XikeStor `SKS3200M-8GPY1XF` switch:
  - Ports: `8+1`
  - Speed: 8 x `2.5Gbps` twisted pair ports and 1 x 10G fiber optic port

### Features

- [x] VPN (Tailscale) Interconnection, Offsite Office, Home Office, Anytime, Anywhere Intranet Access
- [x] Common applications: Gitea, Jellyfin, Paperless...
- [x] Automated bare metal provisioning with PXE boot - [netboot.xyz](https://netboot.xyz/)
- [x] Automated Kubernetes installation and management
- [x] Installing and managing applications using GitOps
- [x] Automatic rolling upgrade for OS and Kubernetes
- [x] Automatically update apps (with approval)
- [x] Modular architecture, easy to add or remove features/components
- [x] Automated certificate management ([Tailscale HTTPS](https://tailscale.com/kb/1153/enabling-https/))
- [x] Automatically update DNS records for exposed services ([Tailscale MagicDNS](https://tailscale.com/kb/1217/tailnet-name))
- [x] Expose services to the internet securely with [Tailscale Funnel](https://tailscale.com/kb/1223/tailscale-funnel)
- [x] CI/CD platform
- [x] Private container registry
- [x] Distributed storage
- [x] Support multiple environments (dev, prod)
- [x] Monitoring and alerting
- [x] Automated backup and restore
- [x] Single sign-on
- [x] Infrastructure testing

Some demo videos and screenshots are shown here.
They can't capture all the project's features, but they are sufficient to get a concept of it.

> 🐾**Notes**
>
> My own demo videos haven't been recorded yet.

|                                                      Demo                                                       |
| :-------------------------------------------------------------------------------------------------------------: |
|                      [![][deploy-demo]](https://asciinema.org/a/xkBRkwC6e9RAzVuMDXH3nGHp7)                      |
|                      Deploy with a single command (after updating the configuration files)                      |
|                          [![][pxe-demo]](https://www.youtube.com/watch?v=y-d7btNNAT8)                           |
|                                                    PXE boot                                                     |
|                                    [![][netboot.xyz-demo]][netboot.xyz-demo]                                    |
|                                                   netboot.xyz                                                   |
|                                     [![][tailscale-demo1]][tailscale-demo1]                                     |
|                                     [![][tailscale-demo2]][tailscale-demo2]                                     |
|                          Tailscale Kubernetes Operator, VPN/Tunnel/DNS/HTTPS/Certs/...                          |
|                                         [![][hubble-demo]][hubble-demo]                                         |
|            Observe network traffic with Hubble, built on top of [Cilium](https://cilium.io) and eBPF            |
|                                       [![][homepage-demo]][homepage-demo]                                       |
|                           Homepage powered by... [Homepage](https://gethomepage.dev)                            |
|                                        [![][grafana-demo]][grafana-demo]                                        |
|                         Monitoring dashboard powered by [Grafana](https://grafana.com)                          |
|                                          [![][gitea-demo]][gitea-demo]                                          |
|                              Git server powered by [Gitea](https://gitea.io/en-us)                              |
|                                         [![][matrix-demo]][matrix-demo]                                         |
|                                    [Matrix](https://matrix.org/) chat server                                    |
|                                     [![][woodpecker-demo]][woodpecker-demo]                                     |
|                     Continuous integration with [Woodpecker CI](https://woodpecker-ci.org)                      |
|                                         [![][argocd-demo]][argocd-demo]                                         |
|                       Continuous deployment with [ArgoCD](https://argoproj.github.io/cd)                        |
|                                          [![][alert-demo]][alert-demo]                                          |
|                               [ntfy](https://ntfy.sh) displaying received alerts                                |
|                                             [![][ai-demo]][ai-demo]                                             |
| Self-hosted AI powered by [Ollama](https://ollama.com) (experimental, not very fast because I don't have a GPU) |

[deploy-demo]: https://asciinema.org/a/xkBRkwC6e9RAzVuMDXH3nGHp7.svg
[pxe-demo]: https://user-images.githubusercontent.com/27996771/157303477-df2e7410-8f02-4648-a86c-71e6b7e89e35.png
[netboot.xyz-demo]: https://netboot.xyz/assets/images/netboot.xyz-d976acd5e46c61339230d38e767fbdc2.gif
[tailscale-demo1]: https://github.com/user-attachments/assets/674e2a2e-e258-46c5-9b22-584ea6ed8b9a
[tailscale-demo2]: https://github.com/user-attachments/assets/23770a79-f48b-402f-b715-9f7a3a7fd451
[hubble-demo]: https://github.com/khuedoan/homelab/assets/27996771/9c6677d0-3564-47c0-852b-24b6a554b4a3
[homepage-demo]: https://github.com/user-attachments/assets/457b5be9-7dc6-4963-802d-5b2220ccd331
[grafana-demo]: https://github.com/khuedoan/homelab/assets/27996771/ad937b26-e9bc-4761-83ae-1c7f512ea97f
[gitea-demo]: https://github.com/khuedoan/homelab/assets/27996771/c245534f-88d9-4565-bde8-b39f60ccee9e
[matrix-demo]: https://user-images.githubusercontent.com/27996771/149448510-7163310c-2049-4ccd-901d-f11f605bfc32.png
[woodpecker-demo]: https://github.com/khuedoan/homelab/assets/27996771/5d887688-d20a-44c8-8f77-0c625527dfe4
[argocd-demo]: https://github.com/khuedoan/homelab/assets/27996771/527e2529-4fe1-4664-ab8a-b9eb3c492d20
[alert-demo]: https://github.com/user-attachments/assets/64be9415-582f-4893-b37e-59b6bce525b2
[ai-demo]: https://github.com/khuedoan/homelab/assets/27996771/d77ba511-00b7-47c3-9032-55679a099e70

### Tech stack

<table>
    <tr>
        <th>Logo</th>
        <th>Name</th>
        <th>Description</th>
    </tr>
    <tr>
        <td><img width="32" src="https://simpleicons.org/icons/ansible.svg"></td>
        <td><a href="https://www.ansible.com">Ansible</a></td>
        <td>Automate bare metal provisioning and configuration</td>
    </tr>
    <tr>
        <td><img width="32" src="https://netboot.xyz/img/nbxyz-laptop.gif"></td>
        <td><a href="https://netboot.xyz">Netboot.xyz</a></td>
        <td>Netboot your favorite operating systems in one place</td>
    </tr>
    <tr>
        <td><img width="32" src="https://avatars.githubusercontent.com/u/30269780"></td>
        <td><a href="https://argoproj.github.io/cd">ArgoCD</a></td>
        <td>GitOps tool built to deploy applications to Kubernetes</td>
    </tr>
    <tr>
        <td><img width="32" src="https://decagon.ai/_next/image?url=%2Favatars%2Ftailscale.png&w=48&q=88"></td>
        <td><a href="https://tailscale.com/kb/1153/enabling-https/">Tailscale HTTPS Certs</a></td>
        <td>Tailscale HTTPS Certificates</td>
    </tr>
    <tr>
        <td><img width="32" src="https://avatars.githubusercontent.com/u/21054566?s=200&v=4"></td>
        <td><a href="https://cilium.io">Cilium</a></td>
        <td>eBPF-based Networking, Observability and Security (CNI, LB, Network Policy, etc.)</td>
    </tr>
    <tr>
        <td><img width="32" src="https://decagon.ai/_next/image?url=%2Favatars%2Ftailscale.png&w=48&q=88"></td>
        <td><a href="https://tailscale.com/kb/1217/tailnet-name">Tailscale MagicDNS</a></td>
        <td>DNS</td>
    </tr>
    <tr>
        <td><img width="32" src="https://decagon.ai/_next/image?url=%2Favatars%2Ftailscale.png&w=48&q=88"></td>
        <td><a href="https://tailscale.com/kb/1223/tailscale-funnel">Tailscale Funnel</a></td>
        <td>Tunnel</td>
    </tr>
    <tr>
        <td><img width="32" src="https://www.docker.com/wp-content/uploads/2022/03/Moby-logo.png"></td>
        <td><a href="https://www.docker.com">Docker</a></td>
        <td>Ephemeral PXE server</td>
    </tr>
    <tr>
        <td><img width="32" src="https://decagon.ai/_next/image?url=%2Favatars%2Ftailscale.png&w=48&q=88"></td>
        <td><a href="https://tailscale.com/kb/1236/kubernetes-operator">Tailscale Kubernetes Operator</a></td>
        <td>Tailscale Kubernetes Operator lets you: K8s API Server Proxy; Ingress; Egress; DNS; Certs...</td>
    </tr>
    <tr>
        <td><img width="32" src="https://assets.ubuntu.com/v1/8114528b-picto-ubuntu-orange.png"></td>
        <td><a href="https://ubuntu.com/server">Ubuntu Server</a></td>
        <td>Base OS for Kubernetes nodes</td>
    </tr>
    <tr>
        <td><img width="32" src="https://upload.wikimedia.org/wikipedia/commons/b/bb/Gitea_Logo.svg"></td>
        <td><a href="https://gitea.com">Gitea</a></td>
        <td>Self-hosted Git service</td>
    </tr>
    <tr>
        <td><img width="32" src="https://grafana.com/static/img/menu/grafana2.svg"></td>
        <td><a href="https://grafana.com">Grafana</a></td>
        <td>Observability platform</td>
    </tr>
    <tr>
        <td><img width="32" src="https://helm.sh/img/helm.svg"></td>
        <td><a href="https://helm.sh">Helm</a></td>
        <td>The package manager for Kubernetes</td>
    </tr>
    <tr>
        <td><img width="32" src="https://avatars.githubusercontent.com/u/49319725"></td>
        <td><a href="https://k3s.io">K3s</a></td>
        <td>Lightweight distribution of Kubernetes</td>
    </tr>
    <tr>
        <td><img width="32" src="https://kanidm.com/images/logo.svg"></td>
        <td><a href="https://kanidm.com">Kanidm</a></td>
        <td>Modern and simple identity management platform</td>
    </tr>
    <tr>
        <td><img width="32" src="https://avatars.githubusercontent.com/u/13629408"></td>
        <td><a href="https://kubernetes.io">Kubernetes</a></td>
        <td>Container-orchestration system, the backbone of this project</td>
    </tr>
    <tr>
        <td><img width="32" src="https://github.com/grafana/loki/blob/main/docs/sources/logo.png?raw=true"></td>
        <td><a href="https://grafana.com/oss/loki">Loki</a></td>
        <td>Log aggregation system</td>
    </tr>
    <tr>
        <td><img width="32" src="https://raw.githubusercontent.com/NixOS/nixos-artwork/refs/heads/master/logo/nix-snowflake-colours.svg"></td>
        <td><a href="https://nixos.org">Nix</a></td>
        <td>Convenient development shell</td>
    </tr>
    <tr>
        <td><img width="32" src="https://ntfy.sh/_next/static/media/logo.077f6a13.svg"></td>
        <td><a href="https://ntfy.sh">ntfy</a></td>
        <td>Notification service to send notifications to your phone or desktop</td>
    </tr>
    <tr>
        <td><img width="32" src="https://avatars.githubusercontent.com/u/3380462"></td>
        <td><a href="https://prometheus.io">Prometheus</a></td>
        <td>Systems monitoring and alerting toolkit</td>
    </tr>
    <tr>
        <td><img width="32" src="https://docs.renovatebot.com/assets/images/logo.png"></td>
        <td><a href="https://www.whitesourcesoftware.com/free-developer-tools/renovate">Renovate</a></td>
        <td>Automatically update dependencies</td>
    </tr>
    <tr>
        <td><img width="32" src="https://raw.githubusercontent.com/rook/artwork/master/logo/blue.svg"></td>
        <td><a href="https://rook.io">Rook Ceph</a></td>
        <td>Cloud-Native Storage for Kubernetes</td>
    </tr>
    <tr>
        <td><img width="32" src="https://avatars.githubusercontent.com/u/84780935?s=200&v=4"></td>
        <td><a href="https://woodpecker-ci.org">Woodpecker CI</a></td>
        <td>Simple yet powerful CI/CD engine with great extensibility</td>
    </tr>
    <tr>
        <td><img width="32" src="https://zotregistry.dev/v2.0.2/assets/images/logo.svg"></td>
        <td><a href="https://zotregistry.dev">Zot Registry</a></td>
        <td>Private container registry</td>
    </tr>
</table>

## Get Started

- [Try it out locally](https://homelab2.e-whisper.com/installation/sandbox) without any hardware (just 4 commands!)
- [Deploy on real hardware](https://homelab2.e-whisper.com/installation/production/prerequisites) for production workload

## Roadmap

See [roadmap](https://homelab2.e-whisper.com/reference/roadmap) and [open issues](https://github.com/east4ming/homelab2/issues) for a list of proposed features and known issues.

## Contributing

Any contributions you make are greatly appreciated.

Please see [contributing guide](https://homelab2.e-whisper.com/reference/contributing) for more information.

## License

Copyright &copy; 2020 - 2024 East4Ming

Distributed under the GPLv3 License.
See [license page](https://homelab2.e-whisper.com/reference/license) or `LICENSE.md` file for more information.

## Acknowledgements

References:

- [Khue's Homelab](https://homelab.khuedoan.com/)
- [Ephemeral PXE server inspired by Minimal First Machine in the DC](https://speakerdeck.com/amcguign/minimal-first-machine-in-the-dc)
- [ArgoCD usage and monitoring configuration in locmai/humble](https://github.com/locmai/humble)
- [README template](https://github.com/othneildrew/Best-README-Template)
- [Run the same Cloudflare Tunnel across many `cloudflared` processes](https://developers.cloudflare.com/cloudflare-one/tutorials/many-cfd-one-tunnel)
- [MAC address environment variable in GRUB config](https://askubuntu.com/questions/1272400/how-do-i-automate-network-installation-of-many-ubuntu-18-04-systems-with-efi-and)
- [Official k3s systemd service file](https://github.com/k3s-io/k3s/blob/master/k3s.service)
- [Official Cloudflare Tunnel examples](https://github.com/cloudflare/argo-tunnel-examples)
- [Initialize GitOps repository on Gitea and integrate with Tekton by RedHat](https://github.com/redhat-scholars/tekton-tutorial/tree/master/triggers)
- [SSO configuration from xUnholy/k8s-gitops](https://github.com/xUnholy/k8s-gitops)
- [Pre-commit config from k8s-at-home/flux-cluster-template](https://github.com/k8s-at-home/flux-cluster-template)
- [Diátaxis technical documentation framework](https://diataxis.fr)
- [Official Terratest examples](https://github.com/gruntwork-io/terratest/tree/master/test)
- [Self-host an automated Jellyfin media streaming stack](https://zerodya.net/self-host-jellyfin-media-streaming-stack)
- [App Template Helm chart by bjw-s](https://bjw-s.github.io/helm-charts/docs/app-template)
- [Various application configurations in onedr0p/home-ops](https://github.com/onedr0p/home-ops)

Here is a list of the contributors who have helped to improve this project.
Big shout-out to them!

- ![](https://github.com/locmai.png?size=24) [@locmai](https://github.com/locmai)
- ![](https://github.com/MatthewJohn.png?size=24) [@MatthewJohn](https://github.com/MatthewJohn)
- ![](https://github.com/karpfediem.png?size=24) [@karpfediem](https://github.com/karpfediem)
- ![](https://github.com/linhng98.png?size=24) [@linhng98](https://github.com/linhng98)
- ![](https://github.com/elliotblackburn.png?size=24) [@elliotblackburn](https://github.com/elliotblackburn)
- ![](https://github.com/dotdiego.png?size=24) [@dotdiego](https://github.com/dotdiego)
- ![](https://github.com/Crimrose.png?size=24) [@Crimrose](https://github.com/Crimrose)
- ![](https://github.com/eventi.png?size=24) [@eventi](https://github.com/eventi)
- ![](https://github.com/Bourne-ID.png?size=24) [@Bourne-ID](https://github.com/Bourne-ID)
- ![](https://github.com/akwan.png?size=24) [@akwan](https://github.com/akwan)
- ![](https://github.com/trangmaiq.png?size=24) [@trangmaiq](https://github.com/trangmaiq)
- ![](https://github.com/tangowithfoxtrot.png?size=24) [@tangowithfoxtrot](https://github.com/tangowithfoxtrot)
- ![](https://github.com/raedkit.png?size=24) [@raedkit](https://github.com/raedkit)
- ![](https://github.com/ClashTheBunny.png?size=24) [@ClashTheBunny](https://github.com/ClashTheBunny)
- ![](https://github.com/retX0.png?size=24) [@retX0](https://github.com/retX0)

If you feel you're missing from this list, please feel free to add yourself in a PR.

## Stargazers over time

[![Stargazers over time](https://starchart.cc/east4ming/homelab2.svg)](https://starchart.cc/east4ming/homelab2)
