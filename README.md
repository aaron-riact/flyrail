# flyrail

Bring-your-own-frontend server-driven UI with a reactpy-style Python API.
Python declares the UI, your React+MUI app renders it, your socket carries
it, your tick drives it.

## Why this exists

`reactpy` owns the whole React tree and its own socket protocol. `rjsf`
owns form rendering but not arbitrary layouts. flyrail splits the problem:

- **Python** (`flyrail/`): declarative element helpers, per-session handler
  registry, per-component memoisation, gated keyed-list diffing, slot
  fast-path. Zero dependencies.
- **JS** (`js/`, `flyrail-renderer`): namespace component registry
  (`import * as MUI`), patch applier, client store with resync, debounced
  inputs. Zero dependencies (React is a peer).

See [docs/features.md](docs/features.md) for what each capability buys you,
with a runnable example each.

## Message flow

```
tick:   render(state) -> tree -> diff -> [] | patch ops -> {chan:ui,type:patch,seq,ops}
click:  {chan:ui,type:action,handlerId,event?} -> dispatch -> mutate state -> next tick emits
hot:    set_slot(name, value) -> {chan:ui,type:slot} (bypasses diff)
gap:    seq skip -> resync-request -> snapshot(state, seq) -> {chan:ui,type:snapshot,tree,slots}
```

## Python quickstart

```python
from flyrail import Layout, Stack, Text, Button
from flyrail.transport import ui_envelope_patch

class Panel:
    def render(self, s):
        return Stack(
            Text(f"speed: {s.speed}"),
            Button("Stop", on_click=self.stop),  # like reactpy
        )
    def stop(self, state, event):
        state.speed = 0

layout = Layout(Panel().render, allowed_types={"Stack", "Text", "Button"})
seq = 0
def on_tick(state):
    global seq
    if ops := layout.tick(state):  # [] on idle ticks: send nothing
        seq += 1
        broadcast(ui_envelope_patch(ops, seq))

def on_ws(msg, state):
    global seq
    if msg.get("chan") == "ui" and msg.get("type") == "action":
        layout.dispatch(msg["handlerId"], state, msg.get("event"))
    elif msg.get("type") == "resync-request":
        seq += 1  # a snapshot takes a seq too, or the next patch reuses it
        broadcast(layout.snapshot(state, seq))
```

## JS quickstart

```tsx
import * as MUI from '@mui/material';
import { createRenderer } from 'flyrail-renderer/react';
import { createStore } from 'flyrail-renderer/store';

const { ServerNode } = createRenderer({ ...MUI });  // auto-registered, no switch
const store = createStore({ onResync: (req) => ws.send(JSON.stringify(req)) });
ws.onmessage = (e) => store.ingest(JSON.parse(e.data));
// render store.getTree() via <ServerNode node={tree} send={...} />
```

## Hosting (pick one)

```python
# 1. Fixed tick you own: Driver replaces the hand-rolled seq counter.
from flyrail import Driver
driver = Driver(layout)
def on_tick(state, version):
    if env := driver.flush(state, version):
        broadcast(env)

# 2. Async host: raw ASGI app, one session per connection. FastAPI:
#    from fastapi import WebSocket; await create_ws_app(Panel().render)(scope, receive, send)
#    (or mount in any ASGI framework; no fastapi dependency in this package)
#    A click on a handler the last patch removed is ignored, and a handler
#    that raises is logged on the "flyrail" logger: neither closes the session.
from flyrail import create_ws_app
app = create_ws_app(Panel().render, state_factory=Sim,
                    on_message=lambda data, state: handle_telemetry(data))

# 3. Naive host (no loop at all): invalidate + flush around every message.
driver.invalidate()
if env := driver.flush(state):
    send(env)
```

## Best practices

1. **Stable keys, never indexes.** `key=item.id` on every list child, both
   sides: Python handler ids and hook state follow the key, React reconciles
   by it. Reorder without keys = full remount + lost focus.
2. **Slots for tick-rate values.** Table rows, labels, progress: `Slot("rows")`
   + `set_slot()` bypass the tree diff. Structure goes through patches (rare),
   values through slots (every tick).
3. **Allowlist both ends.** Python `allowed_types={...}` rejects unknown node
   types; JS `isKnownComponent` renders only functions (filters MUI's
   `colors`, `createTheme`, etc.). Never render `registry[arbitraryString]`.
4. **One render per tick, send only on change.** `tick()` then `if ops:`.
   An unchanged tree returns `[]`, so idle ticks send nothing.
5. **Inputs debounce client-side** (150ms default). Server never sees
   keystroke storms; use `flush()` on submit.
6. **Caller-owned seq, snapshot on gaps.** The tick loop numbers patches, and
   a snapshot takes the next seq too. The store drops stale/duplicates and
   answers a gap, a patch that does not fit its tree, or a first patch that
   is not seq 1 with one snapshot round-trip. Snapshots carry the last slot
   values.
7. **Keep `render(state)` pure and cheap.** No DB, no IO: derive from the
   already-computed tick state. One `Layout` per session.
8. **Safe event defaults, names like the DOM.** `preventDefault` is true
   unless opted out (a reload is session death); `stopPropagation` stays
   opt-in; `throttleMs` rate-caps sliders and guards double-submit. Same
   names as the browser, defaults chosen for the socket.
9. **Mark renders `@pure`, version host state.** Pure renders skip render
   CPU when the version is unchanged (unmarked always re-render: correct by
   default). A `@pure` component is skipped while its arguments are
   unchanged, so pass values, not the host's state object: `Gauge(s.speed)`
   is memoised, `Gauge(s)` re-renders every time because a mutable object
   that is the same object is never trusted to be unchanged. `strict=True`
   double-renders in dev to catch nondeterminism.
10. **Component-local UI state via hooks.** `use_state`/`use_memo`/
    `use_effect` inside `@component` bodies keep collapsed flags and drafts
    out of tick state. A setter schedules the render itself and wakes a
    `Driver`'s run loop, from a handler, an effect, a task or another
    thread. Distinct `key=` per instance, hooks unconditional and
    order-stable, or it raises loudly.
11. **Async handlers via `adispatch`.** Handlers may be `async def` (e.g.
    `await db.save()` on click); sync `dispatch` refuses them loudly instead
    of silently dropping the coroutine. Pattern: `await adispatch(...)`,
    then `invalidate()`.

## Docs

- [How it works](docs/how-it-works.md) — architecture, tick/action/resync
  sequences, render pipeline, hook slots, scheduling, message catalog.

## Layout

```
flyrail/          Python core (stdlib only)
  core.py         Stack/Text/Button/TextField/Slot, @component, @pure
  hooks.py        use_state/use_memo/use_effect keyed slots
  layout.py       registry + diff + dispatch + slots + snapshot
  driver.py       dirty-flag scheduling for tick/async/naive hosts
  asgi.py         framework-free websocket sessions
  transport.py    multiplex envelope + tick sketch
js/               flyrail-renderer (zero-dep ESM + tsx)
  protocol.mjs    envelopes, applyOps, debounce (node-tested)
  store.mjs       seq tracking, gap->resync, slots (node-tested)
  ServerNode.tsx  MUI-bound renderer (imports protocol.mjs)
example/          hmi_demo.py runnable narrative of the wire
tests/            focused unittest suites + public-API loopback
```

## Tests

```
PYTHONPATH=. python3 -m unittest discover -s tests -v   # Python suite
(cd js && npm test)                                      # JS suite
PYTHONPATH=. python3 example/hmi_demo.py                 # narrated wire demo
```

## Non-goals / roadmap

- Not a form validator (use your backend validation + error slots), not a
  JSON-Schema renderer (see rjsf), not a full reactpy replacement (sync
  core with no async effects; bring your own frontend instead of an
  owned tree).
- Roadmap: vitest + React Testing Library for `ServerNode`, `byId/order`
  maps for huge reorderable lists, keystroke `ackSeq` if loss-less input sync
  is ever needed, registry packaging.
