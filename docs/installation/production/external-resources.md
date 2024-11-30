# External resources

!!! info

    These resources are optional(Except Tailscale, homelab2 relies heavily on Tailscale), the homelab2 still works without them but will lack some features like trusted certificates and offsite backup

Although I try to keep the amount of external resources to the minimum, there's still need for a few of them.
Below is a list of external resources and why we need them (also see some [alternatives](#alternatives) below).

| Provider        | Resource            | Purpose                                                         |
| --------------- | ------------------- | --------------------------------------------------------------- |
| Terraform Cloud | Workspace           | Terraform state backend                                         |
| ntfy            | Topic               | External notification service to receive alerts                 |
| Tailscale       | VPN Machines        | Offsite Access, Anywhere Access, Telecommuting                  |
| Tailscale       | Kubernetes Operator | Kubernetes Ingress/Egress/HTTPS/Certs                           |
| Tailscale       | MagicDNS            | DNS/Domains                                                     |
| Tailscale       | Funnel              | Allow route traffic from the wider internet to Tailscale nodes. |
| Tailscale       | HTTPS               | Tailscale HTTPS Certs                                           |

## Create credentials

You'll be asked to provide these credentials on first build.

### Create Terraform workspace

Terraform is stateful, which means it needs somewhere to store its state. Terraform Cloud is one option for a state backend with a generous free tier, perfect for a homelab.

1. Sign up for a [Terraform Cloud](https://cloud.hashicorp.com/products/terraform) account
2. Create a workspace named `homelab-external`, this is the workspace where your homelab state will be stored.
3. Change the "Execution Mode" from "Remote" to "Local". This will ensure your local machine, which can access your lab, is the one executing the Terraform plan rather than the cloud runners.

If you decide to use a [different Terraform backend](https://www.terraform.io/language/settings/backends#available-backends), you'll need to edit the `external/versions.tf` file as required.

### ntfy

- Choose a topic name like <https://ntfy.sh/random_topic_name_here_a8sd7fkjxlkcjasdw33813> (treat it like you password)

### Tailscale

Create a account at <https://tailscale.com>. Then create an auth key and an OAuth client. And edit your tailnet policy file.

> 🐾**Warning**:
>
> This project does not contain any content or automation code for Tailscale ACL (tailnet policy file), please refer to [the official documentation](https://tailscale.com/kb/1018/install-acls) by yourself.
> The reasons are:
>
> 1. I prefer to manage Tailscale ACL through GitHub + GitHub Actions;
> 2. Tailscale ACL contains logic that is not part of this project.
> 3. Terraform Tailscale ACL module can only edit the ACL as a whole, not a piece of it.

## Alternatives

To avoid vendor lock-in, each external provider must have an equivalent alternative that is easy to replace:

- Terraform Cloud:
  - Any other [Terraform backends](https://www.terraform.io/language/settings/backends)
- ntfy:
  - [Self-host your own ntfy server](https://docs.ntfy.sh/install)
  - Any other [integration supported by Grafana Alerting](https://grafana.com/docs/grafana/latest/alerting/alerting-rules/manage-contact-points/integrations/#list-of-supported-integrations)
