# Language

Use these terms exactly.

- Module: thing with interface and implementation.
- Interface: everything caller must know; types, invariants, ordering, errors, config, perf.
- Implementation: code inside module.
- Depth: behavior hidden per unit of interface; deep = high leverage.
- Seam: location of a module interface.
- Adapter: concrete implementation satisfying an interface at a seam.
- Leverage: caller value from depth.
- Locality: maintenance value from concentrated change/bugs/knowledge/tests.

Principles:

- Depth is a property of interface, not implementation size.
- Deletion test: complexity vanishes means pass-through; complexity spreads means useful module.
- Interface is test surface.
- One adapter is hypothetical; two adapters make a real seam.
- Avoid overloaded word `boundary` when seam/interface is meant.
