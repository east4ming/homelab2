# Configuration

Open the [development shell](../../concepts/development-shell.md), which includes all the tools needed:

```sh
nix develop
```

If your Initial controller Linux distribution is Ubuntu, you need to execute the following command:

```sh
# Install nix
sudo apt install -y nix

# Add your normal user to the nix* group
sudo usermod -aG nixbld $USER
sudo usermod -aG nix-users $USER

# Re-login to apply the changes
# You can also run the following command to activate the changes to groups:
newgrp nixbld      
newgrp nix-user

# nix develop
nix develop --extra-experimental-features nix-command --extra-experimental-features flakes
```

Run the following script to configure the homelab:

```sh
make configure
```

!!! example

    <!-- TODO update example input -->

    ```
    Enter your env (prod):
    Text editor (nvim):
    Enter seed repo (github.com/east4ming/homelab2): github.com/example/homelab
    Enter your domain (west-beta.ts.net): example.ts.net
    ```

It will prompt you to edit the inventory:

- `control_plane_endpoint`
- `tailscale_auth_key`
- `tailscale_client_id`
- `tailscale_client_secret`
- `registries_config_yaml`
- IP address: the desired one, not the current one, since your servers have no operating system installed yet
- Disk: based on `/dev/$DISK`, in my case it's `sda`, but yours can be `sdb`, `nvme0n1`...
- Network interface: usually it's `eth0`, mine is `eno1`
- MAC address: the **lowercase, colon separated** MAC address of the above network interface

!!! example

    ```yaml title="metal/inventories/prod.yml"
    --8<--
    metal/inventories/prod.yml
    --8<--
    ```

At the end it will show what has changed. After examining the diff, commit and ~~push~~ the changes.

> 🐾**Warning**:
> 不要将您的任何密钥 PUSH 到 GitHub 公共仓库. 包括不限于:
>
> - `metal/inventories/prod.yml`
>   - `tailscale_auth_key`
>   - `tailscale_client_id`
>   - `tailscale_client_secret`
>   - `registries_config_yaml`
