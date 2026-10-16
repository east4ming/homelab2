# Backup and restore

## Prerequisites

Create an S3 bucket to store backups. You can use AWS S3, RustFS, or
any other S3-compatible provider.

- For AWS S3, your bucket URL might look something like this:
  `https://s3.amazonaws.com/my-homelab-backup`.
- For RustFS, your bucket URL might look something like this:
  `https://my-s3-host.example.com/homelab-backup`.

Follow your provider's documentation to create a service account with the
following policy (replace `my-homelab-backup` with your actual bucket name):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-homelab-backup",
        "arn:aws:s3:::my-homelab-backup/*"
      ]
    }
  ]
}
```

Save the access key and secret key to a secure location, such as a password
manager. While you're at it, generate a new password for Restic encryption and
save it there as well.

!!! example

    I use RustFS for my homelab backups. Here's how I set it up:

    - Create a bucket named `homelab-backup`.
    - Create a service account under Identity -> Service Accounts -> Create
      Service Account:
        - Enable Restrict beyond user policy.
        - Paste the policy above.
        - Click Create and copy the access key and secret key
    - I also set up RustFS replication to store backups in two locations: one in
      my house and one remotely.

## Add backup credentials to global secrets

Add the following to `external/terraform.tfvars`:

```hcl
extra_secrets = {
  restic-password = "xxxxxxxxxxxxxxxxxxxxxxxx"
  restic-s3-bucket = "https://s3.amazonaws.com/my-homelab-backup-xxxxxxxxxx"
  restic-s3-access-key = "xxxxxxxxxxxxxxxx"
  restic-s3-secret-key = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

Then apply the changes:

```sh
make external
```

You may want to back up the `external/terraform.tfvars` file to a secure location as well.

## Add backup configuration for volumes

!!! warning

    Do not run the backup command when building a new cluster where you intend
    to restore backups, as it may overwrite existing backup data. To restore
    data on a new cluster, refer to the [restore from
    backup](#restore-from-backup) section.

For now, you need to run a command to opt-in volumes until we have a better
GitOps solution:

```sh
make backup
```

This command will set up Restic repositories and back up the volumes configured
in `./Makefile`. You can adjust the list there to add or remove volumes from the
backup. You only need to run this command once, the backup configuration will
be stored in the cluster and run on a schedule.

## Check for volumes without a backup

A volume only gets a backup if someone added it to the lists in `./Makefile`,
and nothing warns you when that does not happen. To see which volumes have no
backup path yet:

```sh
./scripts/backup-coverage
```

It compares every PersistentVolumeClaim with the VolSync `ReplicationSource`
objects in the cluster and prints the ones without a backup. VolSync's own cache
volumes (`volsync-src-*-cache`) are skipped, and so are the volumes that are
deliberately not backed up (they are listed with a reason inside the script).
The check exits non-zero when it finds anything else, which means: either the
volume holds data you cannot regenerate — add it to the `backup` and `restore`
targets in `./Makefile` and run `make backup` — or it does not, and it belongs
in the exempt list of the script.

The same inspection by hand:

```sh
kubectl get pvc -A
kubectl get replicationsource -A
```

`ReplicationSource` objects are created by `scripts/backup`, so they live in the
cluster and not in Git. A volume that is missing here is missing its backup,
even if it looks fine in `kubectl get pvc`.

## Restore from backup

The restore process is ad-hoc, you need to run a command to restore application volumes:

```sh
make restore
```

The command above will restore the latest backup of recommended volumes. Like
with backups, you can modify `./Makefile` to adjust the list of volumes you
want to restore.
