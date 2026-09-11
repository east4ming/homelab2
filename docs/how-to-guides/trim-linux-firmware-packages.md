# Trim unneeded Linux firmware packages

Ubuntu 24.04 turned `linux-firmware` into a metapackage that pulls in 18 vendor
sub-packages ([announcement](https://www.omgubuntu.co.uk/2026/09/ubuntu-firmware-split-packages-24-04)).
The four N100 nodes only need a fraction of those blobs, so the rest can be
dropped: roughly **450 MB per node**, and firmware upgrades for the vendors we no
longer ship stop being downloaded.

This guide uses [scripts/firmware-slim](https://github.com/east4ming/homelab2/blob/master/scripts/firmware-slim),
which wraps the whole thing in `audit` / `plan` / `apply`.

## What is kept and what is removed

Kept on every node:

| Package | Why |
| --- | --- |
| `linux-firmware-intel-graphics` | i915 GuC/HuC — the kernel command line has `i915.enable_guc=2` |
| `linux-firmware-intel-misc` | other Intel on-board blocks |
| `linux-firmware-intel-wireless` | `iwlwifi` + Bluetooth (CNVi `8086:54f0` / AX201 on the jumper nodes) |
| `linux-firmware-misc` | catch-all for on-board devices |
| `linux-firmware-realtek` | RTL8111 / RTL8125 NICs on the jumper nodes |
| `linux-firmware-amd-misc` | tiny (257 KB), not worth the risk |
| `firmware-sof-signed` | Intel SOF audio firmware (separate package, not a sub-package) |

Removed on every node — no matching hardware in the cluster:

| Package | Size |
| --- | --- |
| `linux-firmware-nvidia-graphics` | 106 MB |
| `linux-firmware-mellanox-spectrum` | 79 MB |
| `linux-firmware-marvell-prestera` | 73 MB |
| `linux-firmware-qualcomm-misc` | 59 MB |
| `linux-firmware-qualcomm-wireless` | 47 MB |
| `linux-firmware-amd-graphics` | 29 MB |
| `linux-firmware-mediatek` | 24 MB |
| `linux-firmware-qlogic` | 13 MB |
| `linux-firmware-broadcom-wireless` | 11 MB |
| `linux-firmware-marvell-wireless` | 7 MB |
| `linux-firmware-qualcomm-graphics` | 7 MB |
| `linux-firmware-netronome` | 6 MB |

## Why you cannot just `apt remove` a sub-package

`linux-image-generic` depends on the `linux-firmware` metapackage, so removing a
single sub-package takes the metapackage — and with it `linux-generic` and
`linux-image-generic` — down with it:

```console
$ apt-get -s remove linux-firmware-nvidia-graphics
The following packages will be REMOVED:
  linux-firmware linux-firmware-nvidia-graphics linux-generic linux-image-generic
```

Losing the kernel metapackages means the node silently stops receiving kernel
upgrades.

!!! warning

    Instead, install the empty `linux-firmware-minimal` stub
    (`Conflicts`/`Replaces`/`Provides: linux-firmware`) **in the same apt
    transaction**. It satisfies the dependency of the kernel metapackages while
    replacing the metapackage, so the vendor sub-packages can be dropped:

    ```console
    $ apt-get -s install --no-install-recommends linux-firmware-minimal linux-firmware-nvidia-graphics-
    0 upgraded, 1 newly installed, 13 to remove and 0 not upgraded.
    ```

    `--no-install-recommends` is required: `linux-firmware-minimal` recommends all
    18 sub-packages and apt would pull them straight back in.

!!! warning

    Do **not** run `apt autoremove` on these nodes afterwards. Once the
    metapackage is gone, apt considers the kept sub-packages "no longer
    required" and would delete the i915 and Wi-Fi firmware. The script marks them
    `apt-mark manual` first to prevent that, but don't tempt it.

## Prerequisites

- SSH access to the nodes as `casey` (nodes can be listed in
  [metal/inventories/prod.yml](https://github.com/east4ming/homelab2/blob/master/metal/inventories/prod.yml)).
- Passwordless sudo on the nodes.

!!! tip

    If `ssh` fails with `Bad owner or permissions on /etc/ssh/ssh_config.d/...`,
    pass extra ssh options through the environment:

    ```sh
    SSH_OPTS='-F /dev/null' ./scripts/firmware-slim audit
    ```

## Audit

Read-only report of every node: OS, installed firmware packages with sizes,
non-Intel hardware, Wi-Fi/Bluetooth, drivers in use, disk usage.

```sh
./scripts/firmware-slim audit
```

## Preview

Show the exact apt transaction that `apply` would run, using `apt-get -s`. The
script refuses to continue if the transaction would remove `linux-generic` or
`linux-image-generic`.

```sh
./scripts/firmware-slim plan
```

Review the output: you want `1 newly installed, 13 to remove` and no mention of
`linux-generic` / `linux-image-generic` in the `will be REMOVED` block.

## Apply

```sh
./scripts/firmware-slim apply
```

You are asked to type `yes` before anything happens (no TTY means it refuses
unless you pass `--yes`). For each node the script:

1. runs `apt-mark manual` on the packages that are kept;
2. re-runs the simulation and aborts on any surprise;
3. runs `apt-get install --no-install-recommends -y linux-firmware-minimal <dropped packages>-`;
4. prints the remaining firmware packages, the state of `linux-image-generic`
   and the disk usage.

A single node can be targeted by naming it, e.g.
`./scripts/firmware-slim apply n100-cheshi-0`.

## Verify

```sh
ssh n100-jumper-0 'dpkg -l "linux-firmware*" | awk "/^ii/{print \$2}"'
ssh n100-jumper-0 'dpkg -s linux-image-generic | grep -E "^(Status|Depends)"'
ssh n100-jumper-0 'df -h /'
```

After the next reboot, confirm nothing is missing:

```sh
ssh n100-jumper-0 'journalctl -b -k | grep -iE "firmware.*(fail|error)|iwlwifi|i915.*(GuC|HuC)"'
```

## Rollback

```sh
# one vendor back
sudo apt-get install linux-firmware-mediatek
# or everything back (the metapackage conflicts with linux-firmware-minimal)
sudo apt-get install linux-firmware
```

## Notes

- `amd64-microcode` looks like a candidate but is a dependency of
  `linux-image-generic` too, so removing it has the same metapackage problem.
  Leave it alone.
- If a node later gets a card that needs one of the removed blobs, install the
  matching sub-package (`sudo apt-get install linux-firmware-mediatek`) — no
  reboot of the whole fleet needed.
- Do not install the `linux-firmware` metapackage again; it conflicts with
  `linux-firmware-minimal` and would pull all 18 sub-packages back in.
