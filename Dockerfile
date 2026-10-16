FROM docker.io/library/python:3.13-slim AS build

WORKDIR /src

# requirements.txt is the single source of truth for the docs toolchain
COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt

COPY . .

RUN mkdocs build --strict

FROM docker.io/library/nginx:1.27-alpine

COPY --from=build /src/site /usr/share/nginx/html
