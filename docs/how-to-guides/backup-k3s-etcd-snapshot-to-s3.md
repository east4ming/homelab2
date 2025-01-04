# Backup K3s Etcd Snapshot To S3

## Prerequisites

Create an S3 bucket named: `k3s-etcd-snapshot` (sure you can change it) to store backups.
You can use AWS S3, Minio, or any other S3-compatible provider.

- For AWS S3, your bucket URL might look something like this:
  `https://s3.amazonaws.com/my-homelab-backup`.
- For Minio, your bucket URL might look something like this:
  `https://my-s3-host.example.com/homelab-backup`.

Please refer to the documentation [Backup and restore](#backup-and-restore) more details.

## Enable k3s etcd s3 backup

Config the `metal/group_vars/all.yml`, add the following:

```yaml
etcd_s3: true
```

Then the `metal/roles/k3s/defaults/main.yml` will add 2 new variables to enable etcd s3 backup.

```yaml
  etcd-s3: true
  etcd-s3-config-secret: k3s-etcd-snapshot-s3-config
```

## Add backup credentials to global secrets

Add the following to `external/terraform.tfvars`:

```hcl
extra_secrets = {
  etcd-s3-endpoint = "s3.amazonaws.com"
  etcd-s3-access-key = "xxxxxxxxxxxxxxxx"
  etcd-s3-secret-key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  etcd-s3-bucket = "k3s-etcd-snapshot"
  etcd-s3-insecure = "false"
  etcd-s3-endpoint-ca = ""
  etcd-s3-endpoint-ca-name =  ""
  etcd-s3-skip-ssl-verify = "false"
  etcd-s3-folder = "folder"
  etcd-s3-region = "us-east-1"
  etcd-s3-timeout = "5m"
  etcd-s3-proxy = ""
}
```

Then apply the changes:

```sh
make external
```

You may want to back up the `external/terraform.tfvars` file to a secure location as well.

!!! warning

    TODO:
    This feature has not yet been fully realized. Currently, you need to refer to [How secrets are pulled from global secrets to other namespaces](#secrets-management) to create it manually.
