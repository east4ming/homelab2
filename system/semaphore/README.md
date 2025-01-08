# Semaphore

## Admin Password

🐾Warning:

To ensure that the password is security, we only set the admin's username(aka: `admin`) in the ENV, not set the password.
After the semaphore pod is started, you need to log in to the pod, execute the following command to change the password manually, and then log in again.

```bash
$ semaphore user change-by-login --login admin --name Admin --email cuikaidong@foxmail.com --password changeme
Loading config
Validating config
User admin <cuikaidong@foxmail.com> changed!
```

## TODO:

- [x] Enable `email_alert`

## Enable `email_alert`

> The reason for this is to avoid leakage of smtp related accounts.

After enable config pvc, you can edit the `config.yml` to enable `email_alert` and other configs.

Edit the `/etc/semaphore/config.yml`, append the following configs.

```json
{
  ...,
  "email_sender": "sender@example.com",
  "email_host": "smtp.example.com",
  "email_port": "465",
  "email_secure": true,
  "email_username": "sender@example.com",
  "email_password": "changeit"
}
```

## 📚References

- <https://docs.semaphoreui.com/administration-guide/installation/docker/>
- <https://github.com/semaphoreui/semaphore/tree/develop/deployment>
- <https://docs.semaphoreui.com/administration-guide/configuration/>
- <https://github.com/bjw-s/helm-charts/tree/main/charts>
