# Changelog

Covers both halves: `flyrail` (Python) and `flyrail-renderer` (JS).

## Unreleased

### Breaking

- **Unkeyed handler ids changed shape.** An index path segment is now written
  `#0`, so `0.0:on_click:` becomes `0.#0:on_click:`. Keyed ids are unchanged.
  Ids are opaque and rebuilt every render; only code that matched them as
  strings needs updating.
- **A mutable argument that is the same object is never memoised.**
  `Gauge(state)` on a `@pure` component now re-renders every time, because an
  in-place change makes old and new compare equal. Pass values instead —
  `Gauge(state.speed)` is memoised as before. A frozen dataclass passed as-is
  is also treated as changed.
- **`allowed_types=set()` allows nothing.** It used to turn the allowlist off.
  Only `None` means "no allowlist".
- **`dispatch`/`adispatch` mark the layout dirty.** A tick host should pass
  its version token every tick and stop calling `invalidate()` per tick, which
  kept the version gate from ever skipping a render.
- **`create_ws_app` no longer lets exceptions end the session.** A raising
  handler, a failed render and a frame that is not JSON are logged on the
  `flyrail` logger instead.
- **`createRenderer` lives at `flyrail-renderer/react`**, as `package.json`
  always said; the docs imported it from the package root.

### Added

- `create_ws_app(allowed_origins=...)` refuses websockets from unlisted
  origins (code 1008). Set it in production.
- `Layout.snapshot()` carries the last slot values as `slots`.
- `createSlotHub()`, `store.slots` and `createRenderer(registry, { slots })`:
  share the store's slots with the renderer so slot and snapshot values reach
  every `Slot`.
- `Layout.on_schedule`: called when the layout becomes dirty from a handler or
  hook; `Driver` uses it to wake `run()`.
- Tests for `ServerNode.tsx` under vitest and React Testing Library (dev-only
  dependencies), and CI on Python 3.10–3.14.

### Fixed

- A click could run another button's handler when an unkeyed child and a
  sibling keyed with its index shared a path.
- Hook state of an unkeyed component stayed at the old index when its keyed
  parent moved.
- A `@pure` component given the host's state object never re-rendered.
- `set_state` from `use_effect` did not schedule a render.
- `Driver.invalidate()` from another thread did not wake the loop, and hook
  setters never woke it at all.
- A render that raised froze an ASGI session and emptied the handler registry.
- A stale click, a raising handler or a malformed frame closed the ASGI session.
- Slot values were blank after a resync or on a new connection.
- The store never recovered from a mid-stream first patch or a patch that did
  not fit its tree.
- The README quickstart reused a seq for its resync snapshot, so the client
  dropped the next patch.
- `on_change=` on anything but `TextField`, and dict props with non-string
  keys, broke serialization.
- Every `Button` rendered without its label.
- Typing into a server-valued `TextField` was reverted until the echo arrived.
- A pending text edit was lost or sent late when its input unmounted.
- `npm test` could not find its files, and 13 Python tests were never
  collected by CI (plus 6 more that failed to import without pytest).

### Performance

- Patches apply copy-on-write: untouched subtrees keep their identity.
- `ServerNode` is memoised, so a patch re-renders only the nodes it changed.
  Pass a stable `send`.
