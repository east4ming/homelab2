# syntax=docker/dockerfile:1

FROM ghcr.io/astral-sh/uv:0.13.6 AS uv

FROM docker.io/library/python:3.13-slim AS build

WORKDIR /src

# pyproject.toml + uv.lock are the single source of truth for the docs toolchain
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --only-group docs

COPY . .

RUN .venv/bin/mkdocs build --strict

FROM docker.io/library/nginx:1.27-alpine

COPY --from=build /src/site /usr/share/nginx/html
