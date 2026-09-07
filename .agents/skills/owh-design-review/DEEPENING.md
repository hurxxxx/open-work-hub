# Deepening

Dependency categories:

- In-process: pure/in-memory; merge and test directly.
- Local-substitutable: use existing local stand-in such as test DB or in-memory FS.
- Remote owned: define port plus production adapter and test adapter.
- True external: inject port and mock external adapter.

Rules:

- One adapter = hypothetical seam; two adapters = real seam.
- Keep internal seams private.
- Replace shallow unit tests with tests at the deepened interface.
- Assert observable outcomes, not internals.
