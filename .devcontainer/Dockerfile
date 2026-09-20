# Dev image for the MMA API service.
#
# Deliberately separate from the production Dockerfile: that image is a hardened
# runtime (no uv, no git, non-root `appuser`, source baked in) and cannot host a
# dev container. Both images share the same pinned Debian 13 (trixie) base so the
# dev and production toolchains stay aligned.

FROM node:24-trixie-slim@sha256:8ec5d7557396cfe32d21c3f9c13072355ceab22b584578ca4bb28af31120cffe AS node

FROM python:3.13-slim@sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0

# uv comes from the same pinned release the production image and mise.toml use.
COPY --from=ghcr.io/astral-sh/uv:0.12.17@sha256:10787c682e4184e4f290de1171fd4703dc63de99221f10fe1c99002ce7fa9acc /uv /uvx /usr/local/bin/

# Node 24 for `just check` (node --test, node --check). Copied from the Docker
# Official node image rather than a third-party apt repo.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gh \
        git \
        less \
        ssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf /usr/local/lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Non-root user. uid/gid 1000 matches the typical rootful Linux/macOS host user;
# devcontainer.json sets updateRemoteUserUID so bind-mounted files stay writable.
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000
RUN groupadd --gid "${USER_GID}" "${USERNAME}" \
    && useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home --shell /bin/bash "${USERNAME}" \
    && install -d -o "${USERNAME}" -g "${USERNAME}" \
        "/home/${USERNAME}/.cache/uv" \
        "/home/${USERNAME}/.venv"

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/home/${USERNAME}/.local/bin:${PATH}"

USER ${USERNAME}

# `just` is the project task runner but is not packaged in Debian trixie.
# Installing the PyPI distribution via uv keeps it pinned and arch-portable
# (x86_64 and arm64 hosts both resolve a matching wheel).
RUN uv tool install rust-just==1.58.0
