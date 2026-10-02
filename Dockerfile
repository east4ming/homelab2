FROM docker.io/library/python:3.13-slim AS build

WORKDIR /src

RUN pip install --no-cache-dir mkdocs-material

COPY . .

RUN mkdocs build

FROM docker.io/library/nginx:1.27-alpine

COPY --from=build /src/site /usr/share/nginx/html
