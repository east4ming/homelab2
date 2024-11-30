# Updating documentation (this website)

This project uses the [Diátaxis](https://diataxis.fr) technical documentation framework.
The website is generated using [Material for MkDocs](https://squidfunk.github.io/mkdocs-material) and can be viewed at [homelab2.e-whisper.com](https://homelab2.e-whisper.com).

There are 4 main parts:

- [Getting started (tutorials)](https://diataxis.fr/tutorials): learning-oriented
- [Concepts (explanation)](https://diataxis.fr/explanation): understanding-oriented
- [How-to guides](https://diataxis.fr/how-to-guides): goal-oriented
- [Reference](https://diataxis.fr/reference): information-oriented

## Local development

To edit and view locally, run:

```sh
make docs
```

Then visit [localhost:8000](http://localhost:8000)

## Deployment

For stability and performance, it's running on [Cloudflare Pages](https://developers.cloudflare.com/pages/).

To deploy, see this documentation: [MkDocs · Cloudflare Pages docs](https://developers.cloudflare.com/pages/framework-guides/deploy-an-mkdocs-site/#_top).

Steps like below:

![MkDocs Deploy On Cloudflare Pages](TODO:)
