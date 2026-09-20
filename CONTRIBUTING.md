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
