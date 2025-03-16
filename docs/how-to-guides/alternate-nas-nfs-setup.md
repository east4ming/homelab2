# Alternate NAS NFS Setup

This is a guide on how to setup an alternate NFS client(csi-driver-nfs) for the NAS NFS server.

## Prerequisites

* A working NAS NFS server setup.

## Setup

1. Install the [csi-driver-nfs](https://github.com/kubernetes-csi/csi-driver-nfs)
2. For specific details, see `system/csi-driver-nfs`; here, I use the static mode according to my personal needs.
3. Create a static PV, static PVC, Deployment, and then you can use NFS storage. For specific details, see `apps/jellyfin/templates/pv-anothervideos.yaml` and `apps/jellyfin/templates/pvc-anothervideos.yaml` as well as the `anothervideos` section of `apps/jellyfin/values.yaml`.

## Reference

* [csi-driver-nfs/charts/README.md at v4.10.0 · kubernetes-csi/csi-driver-nfs](https://github.com/kubernetes-csi/csi-driver-nfs/blob/v4.10.0/charts/README.md)
* [csi-driver-nfs/charts/v4.10.0/csi-driver-nfs/values.yaml at master · kubernetes-csi/csi-driver-nfs](https://github.com/kubernetes-csi/csi-driver-nfs/blob/master/charts/v4.10.0/csi-driver-nfs/values.yaml)
* [csi-driver-nfs/deploy/example/README.md at v4.10.0 · kubernetes-csi/csi-driver-nfs](https://github.com/kubernetes-csi/csi-driver-nfs/blob/v4.10.0/deploy/example/README.md)
