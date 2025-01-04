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

- [ ] Enable `email_alert`

## 📚References

- <https://docs.semaphoreui.com/administration-guide/installation/docker/>
- <https://github.com/semaphoreui/semaphore/tree/develop/deployment>
- <https://docs.semaphoreui.com/administration-guide/configuration/>
- <https://github.com/bjw-s/helm-charts/tree/main/charts>
