# User onboarding

=== "For user"

    ## Create user

    Ask an admin to create your account, provide the following information:

    - [ ] Full name (John Doe)
    - [ ] Select a username (`johndoe`)
    - [ ] Email address (`johndoe@example.com`)

    ## Install companion apps

    For all users:

    - [ ] A password manager (I personally recommend [Bitwarden](https://bitwarden.com/download))
    - [ ] A [Matrix chat client](https://matrix.org/clients) (optional, you can use the web version)

    For technical users:

    - [ ] [Docker](https://docs.docker.com/engine/install)
    - [ ] [mise](https://mise.jdx.dev) and [uv](https://docs.astral.sh/uv/) (required for local development)
    - [ ] [Lens](https://k8slens.dev) (optional, you can use the included `kubectl` or `k9s` command in the tools container)

=== "For admin"

    Run the following script:

    ```sh
    ./scripts/onboard-user johndoe "John Doe" "johndoe@example.com"
    ```

    Let the user scan the QR code or follow the link to set up passkeys or password + TOTP.
