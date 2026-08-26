# UI Prototype

Use for visual/design questions.

## Shape

- Prefer existing route with `?variant=`; keep real data/auth and swap rendering only.
- New throwaway route only when no existing host exists.
- Default 3 variants, max 5.
- Variants must differ structurally, not only color/copy.
- Use existing component library/styling.
- Floating switcher updates URL, supports left/right keys, ignores focused inputs, hidden in production.

## Handoff

- Give URL and variant keys.
- After decision, delete losing variants/switcher and rewrite winner as normal production code.
- Do not wire prototypes to real mutations unless the prototype question requires it; use stubs.
