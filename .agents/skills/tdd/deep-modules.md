# Deep Modules

- Deep module = small interface with substantial behavior hidden behind it.
- Shallow module = interface nearly as complex as implementation.
- Prefer modules whose public interface gives high leverage and concentrates change.
- Deletion test: if deleting module removes complexity, it was pass-through; if complexity spreads to callers, it had value.
