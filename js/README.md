# flyrail renderer (JS side)

`createRenderer(registry)` maps Python `{type, props, children, key}`
descriptors to real components. No switch statement: with
`import * as MUI from '@mui/material'` every export is looked up by
`node.type` string.

## Contract

- Unknown `type` renders `null` (`isKnownComponent` also filters out
  non-function MUI exports like `colors`).
- `key` comes from Python `key=` (stable item id). Reorders therefore
  reconcile client-side without remounts or focus loss.
- `on_click` / `on_change` carry `{handlerId, preventDefault,
  stopPropagation, throttleMs?}`; clicks send `{chan:'ui', type:'action',
  handlerId}`, inputs add `event:{value}`. `preventDefault` is true unless
  the descriptor opts out; inputs debounce at 150ms unless `throttleMs`
  selects slider-style throttling (leading + trailing latest).
- `__Slot__` nodes subscribe by name; tick-rate values arrive as
  `{chan:'ui', type:'slot'}` and update without a tree patch.
- For prod bundles prefer an explicit allowlist
  (`createRenderer({Button, TextField})`) over the full namespace import
  to keep tree-shaking.

## Tests

`npm test` runs both halves. `node --test` covers the wire logic in
`protocol.mjs` and `store.mjs`, which `ServerNode.tsx` imports (tested code =
shipped code); vitest with React Testing Library renders `ServerNode.tsx`
itself in jsdom, against plain stand-ins for the MUI components. The test
tooling is dev-only: the published package still has no dependencies.
