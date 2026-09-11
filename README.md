# pyforms

Bring-your-own-frontend server-driven UI with a reactpy-style Python API.
Python declares the UI, your React+MUI app renders it, your socket carries
it, your tick drives it.

## Why this exists

`reactpy` owns the whole React tree and its own socket protocol. `rjsf`
owns form rendering but not arbitrary layouts. pyforms splits the problem:

- **Python** (`pyforms/`): declarative element helpers, per-session handler
  registry, hash-gated diffing, slot fast-path. Zero dependencies.
- **JS** (`js/`, `pyforms-renderer`): namespace component registry
  (`import * as MUI`), patch applier, client store with resync, debounced
  inputs. Zero dependencies (React is a peer).

## Message flow

```
tick:   render(state) -> tree -> diff -> [] | patch ops -> {chan:ui,type:patch,seq,ops}
click:  {chan:ui,type:action,handlerId,event?} -> dispatch -> mutate state -> next tick emits
hot:    set_slot(name, value) -> {chan:ui,type:slot} (bypasses diff)
gap:    seq skip -> resync-request -> snapshot(state, seq) -> {chan:ui,type:snapshot,tree}
```

## Python quickstart

```python
from pyforms import Layout, Stack, Text, Button
from pyforms.transport import ui_envelope_patch

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
    if msg.get("chan") == "ui" and msg.get("type") == "action":
        layout.dispatch(msg["handlerId"], state, msg.get("event"))
    elif msg.get("type") == "resync-request":
        broadcast(layout.snapshot(state, seq + 1))
```

## JS quickstart

```tsx
import * as MUI from '@mui/material';
import { createRenderer } from 'pyforms-renderer';
import { createStore } from 'pyforms-renderer/store';

const { ServerNode } = createRenderer({ ...MUI });  // auto-registered, no switch
const store = createStore({ onResync: (req) => ws.send(JSON.stringify(req)) });
ws.onmessage = (e) => store.ingest(JSON.parse(e.data));
// render store.getTree() via <ServerNode node={tree} send={...} />
```

## Best practices

1. **Stable keys, never indexes.** `key=item.id` on every list child, both
   sides: Python handler ids embed the key, React reconciles by it. Reorder
   without keys = full remount + lost focus.
2. **Slots for tick-rate values.** Table rows, labels, progress: `Slot("rows")`
   + `set_slot()` bypass the tree diff. Structure goes through patches (rare),
   values through slots (every tick).
3. **Allowlist both ends.** Python `allowed_types={...}` rejects unknown node
   types; JS `isKnownComponent` renders only functions (filters MUI's
   `colors`, `createTheme`, etc.). Never render `registry[arbitraryString]`.
4. **One render per tick, send only on change.** `tick()` then `if ops:`.
   Hash-gating makes idle ticks free.
5. **Inputs debounce client-side** (150ms default). Server never sees
   keystroke storms; use `flush()` on submit.
6. **Caller-owned seq, snapshot on gaps.** The tick loop numbers patches; the
   store drops stale/duplicates and answers gaps with one snapshot round-trip.
7. **Keep `render(state)` pure and cheap.** No DB, no IO: derive from the
   already-computed tick state. One `Layout` per session.

## Layout

```
pyforms/          Python core (stdlib only)
  core.py         Stack/Text/Button/TextField/Slot, @component
  layout.py       registry + diff + dispatch + slots + snapshot
  transport.py    multiplex envelope + tick sketch
js/               pyforms-renderer (zero-dep ESM + tsx)
  protocol.mjs    envelopes, applyOps, debounce (node-tested)
  store.mjs       seq tracking, gap->resync, slots (node-tested)
  ServerNode.tsx  MUI-bound renderer (imports protocol.mjs)
example/          hmi_demo.py runnable narrative of the wire
tests/            focused unittest suites + public-API loopback
```

## Tests

```
PYTHONPATH=. python3 -m unittest discover -s tests -v   # 32 tests
node --test js/protocol.test.mjs js/store.test.mjs      # 17 tests
PYTHONPATH=. python3 example/hmi_demo.py                 # narrated wire demo
```

## Non-goals / roadmap

- Not a form validator (use your backend validation + error slots), not a
  JSON-Schema renderer (see rjsf), not a full reactpy replacement (no hooks;
  tick state replaces `use_state`).
- Roadmap: vitest + React Testing Library for `ServerNode`, `byId/order`
  maps for huge reorderable lists, keystroke `ackSeq` if loss-less input sync
  is ever needed, registry packaging.
