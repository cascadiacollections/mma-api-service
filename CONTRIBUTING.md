# Contributing

## Development

Use the included devcontainer or install Python 3.12+, `uv`, Node.js, and
`just`.

```bash
just setup
just dev
```

The API and interface are available at <http://127.0.0.1:8000>. OpenAPI
documentation is available at `/docs`.

## Editors

Project settings for Zed live in `.zed/` (ruff formatting on save, pyright +
ruff language servers, `.venv` detection, and `just` tasks via the task
picker). VS Code settings ship with the dev container.

If you run Zed as a Flatpak, its sandbox does not inherit your shell `PATH`, so
`just`/`uv`/`node` tasks fail until you grant access. For example:

```bash
flatpak override --user \
  --filesystem=/home/linuxbrew:ro \
  --env=PATH="/app/bin:/usr/bin:/home/linuxbrew/.linuxbrew/bin:$HOME/.local/bin" \
  dev.zed.Zed
```

Adjust the paths to wherever your toolchain lives. Note that `mise` shims may
not resolve inside the sandbox; point at a concrete install directory (for
example `~/.local/share/mise/installs/node/24/bin`) instead. Undo with
`flatpak override --user --reset dev.zed.Zed`.

## Before submitting a change

```bash
just check
just container-build
```

Keep changes focused, update tests for behavior changes, and preserve the
stateless URL-sharing format. Avoid adding upstream requests to browser code;
external event data must flow through the cached server adapter.

## Pull requests

Explain the user-visible behavior, operational impact, and validation
performed. Do not commit credentials or production configuration values.
