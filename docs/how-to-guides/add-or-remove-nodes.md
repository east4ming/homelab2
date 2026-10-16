# Add or remove nodes

Or how to scale vertically. To replace the same node with a clean OS, remove it and add it again.

## Add new nodes

!!! tip

    You can add multiple nodes at the same time

Two places to edit —— 拓扑（名称、IP、磁盘、网卡）进 inventory，**真实 MAC 进那个
不进版本控制的 secrets 文件**（公开仓库里不要出现真实 MAC，#550）：

```diff title="metal/inventories/prod.yml"
diff --git a/metal/inventories/prod.yml b/metal/inventories/prod.yml
index 7f6474a..1bb2cbc 100644
--- a/metal/inventories/prod.yml
+++ b/metal/inventories/prod.yml
@@ -8,3 +8,4 @@ metal:
     workers:
       hosts:
         metal3: {ansible_host: 192.168.1.113, mac: "{{ metal_macs['metal3'] }}", disk: sda, network_interface: eno1}
+        metal4: {ansible_host: 192.168.1.114, mac: "{{ metal_macs['metal4'] }}", disk: sda, network_interface: eno1}
```

```diff title="metal/inventories/group_vars/all/zz-secrets.yml"
diff --git a/metal/inventories/group_vars/all/zz-secrets.yml b/metal/inventories/group_vars/all/zz-secrets.yml
--- a/metal/inventories/group_vars/all/zz-secrets.yml
+++ b/metal/inventories/group_vars/all/zz-secrets.yml
@@ -1,3 +1,4 @@
 metal_macs:
   metal3: "aa:bb:cc:00:00:03"
+  metal4: "aa:bb:cc:00:00:04"
```

这个文件被 gitignore，MAC 放哪里、真实值怎么取见
[metal/README.md](../../metal/README.md)。

Install the OS and join the cluster:

```
make metal
```

That's it!

## Remove a node

!!! danger

    It is recommended to remove nodes one at a time

Remove it from the inventory:

```diff title="metal/inventories/prod.yml"
diff --git a/metal/inventories/prod.yml b/metal/inventories/prod.yml
index 7f6474a..d12b50a 100644
--- a/metal/inventories/prod.yml
+++ b/metal/inventories/prod.yml
@@ -4,7 +4,6 @@ metal:
       hosts:
         metal0: {ansible_host: 192.168.1.110, mac: "{{ metal_macs['metal0'] }}", disk: sda, network_interface: eno1}
         metal1: {ansible_host: 192.168.1.111, mac: "{{ metal_macs['metal1'] }}", disk: sda, network_interface: eno1}
-        metal2: {ansible_host: 192.168.1.112, mac: "{{ metal_macs['metal2'] }}", disk: sda, network_interface: eno1}
     workers:
       hosts:
         metal3: {ansible_host: 192.168.1.113, mac: "{{ metal_macs['metal3'] }}", disk: sda, network_interface: eno1}
```

（它在 `zz-secrets.yml` 的 `metal_macs` 里的条目可以顺手删掉，留着不影响运行。）

Drain the node:

```sh
kubectl drain ${NODE_NAME} --delete-emptydir-data --ignore-daemonsets --force
```

Remove the node from the cluster

```sh
kubectl delete node ${NODE_NAME}
```

Shutdown the node:

```
ssh root@${NODE_IP} poweroff
```
