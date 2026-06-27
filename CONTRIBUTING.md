# Contributing

AeroRoute MLX is split across versioned repositories. Keep changes inside the
owning repository and update contracts before consumers.

1. Create a focused branch from `main`.
2. Run `make check` before opening a pull request.
3. Include tests for changed behavior and document cross-repository impact.
4. Do not commit secrets, model weights, downloaded datasets, or build output.
5. Preserve the non-operational simulator disclaimer in user-facing changes.

