# Interface Design For Testing

- Accept dependencies; do not create external clients internally.
- Return results; avoid hidden side effects.
- Keep surface small: fewer methods, fewer parameters, stable invariants.
- Test at the same interface callers use.
