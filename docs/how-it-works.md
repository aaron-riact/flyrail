# How flyrail works

Python declares the UI. Your React app renders it. Your socket carries it.
Your tick (or event loop) drives it. This page traces every path a pixel
and a click can take. Start with `example/hmi_demo.py` for the narrated
version of the same flows.

## Big picture

```mermaid
flowchart LR
    SIM["host state<br/>(sim snapshot, db row, script arg)"]
    LAY["Layout<br/>render + serialize"]
    DIFF["gates + diff"]
    SOCK["your socket<br/>chan ui"]
    STORE["createStore<br/>seq + slots"]
    MUI["ServerNode<br/>MUI registry"]
    ACT["dispatch / adispatch"]

    SIM --> LAY --> DIFF --> SOCK --> STORE --> MUI
    MUI -- "action handlerId" --> SOCK
    SOCK -- "action handlerId" --> ACT
    ACT -- "mutate + invalidate" --> SIM
```

There are exactly two loops: state flows down as trees and patches,
actions flow up as handler ids. Nothing else crosses the wire.

## Message catalog

| Message | Direction | Shape | Purpose |
|---|---|---|---|
| `patch` | server to client | `{chan, type, seq, ops}` | Tree diff since last send |
| `slot` | server to client | `{chan, type, name, value}` | Hot value bypassing the diff |
| `snapshot` | server to client | `{chan, type, seq, tree, slots}` | Full tree and last slot values (first paint, gap recovery) |
| `action` | client to server | `{chan, type, handlerId, event?}` | Click / change with optional value |
| `resync-request` | client to server | `{chan, type}` | "I skipped a seq, send snapshot" |

## Tick loop

```mermaid
sequenceDiagram
    participant T as "tick loop"
    participant L as "Layout"
    participant S as "socket"
    participant C as "store"
    T->>L: "tick(state, version)"
    alt "pure, same version, clean"
        L-->>T: "empty (no render)"
    else "rendered"
        L->>L: "expand (memo), serialize (cache)"
        alt "tree unchanged"
            L-->>T: "empty (no send)"
        else "changed"
            L-->>T: "ops"
            T->>S: "patch seq N ops"
            S->>C: "patch seq N ops"
            C->>C: "seq check, applyOps"
        end
    end
```

Four gates, tried cheapest first, saving different things. **Version-skip**
avoids the render outright when the host passes an unchanged token and the
root is `@pure`. **Memoisation** skips the body of any `@pure` component whose
arguments are unchanged and under which nothing went stale, so a moved token
still only re-runs what moved. **Identity** settles the diff with one `is` when
a render reused every subtree it had. **Compare** is the backstop: an `==`
against the committed tree, needing no cooperation at all.

Any of them can fire alone (see the `invalidate` test: re-render with nothing
to send). `@pure` is a declared contract — output is a function of arguments
and hook slots — and is what opts a component into the first two. Unmarked
components always re-render, so this is correct by default, and `strict=True`
double-renders in dev to catch nondeterminism (it also disables reuse, since a
cache would quietly turn the double-render into one).

The compare is a compare, not a digest: the committed tree is retained anyway
to diff against, so comparing it costs less than hashing it and cannot collide
— which a digest over `json.dumps(default=str)` could, silently dropping an
update between two values that stringified alike.

## Cold path vs hot path

```mermaid
flowchart TD
    Q["per-tick value?"]
    Q -- "rare, structural" --> C["render tree, diff, patch"]
    Q -- "every tick, values" --> H["Slot + set_slot"]
    C --> P["patch envelope, seq"]
    H --> SL["slot envelope, compare dedupe"]
```

Rule of thumb: structure goes through patches, values through slots. A
table whose rows update at 60Hz is a `Slot("rows")`; a dialog opening is a
patch.

## Action round-trip

```mermaid
sequenceDiagram
    participant U as "user"
    participant R as "ServerNode"
    participant S as "socket"
    participant H as "host"
    participant L as "Layout"
    U->>R: "click or type"
    R->>R: "preventDefault, stopPropagation"
    R->>R: "debounce input, throttle slider"
    R->>S: "action handlerId + event"
    S->>H: "action handlerId + event"
    H->>L: "adispatch (await if async)"
    H->>L: "invalidate"
    L-->>H: "flush gives patch seq N"
    H->>S: "patch seq N"
    S->>R: "patch seq N"
```

Notes: `preventDefault` runs synchronously in the React handler (a debounced
callback can no longer cancel the event). Async handlers are awaited before
invalidate so the re-render sees the saved state. Sync `dispatch` refuses
async handlers loudly instead of dropping the coroutine.

## Gap recovery

```mermaid
sequenceDiagram
    participant C as "store"
    participant S as "socket"
    participant H as "host"
    C->>C: "seq 5 arrives after 3: skip apply"
    C->>S: "resync-request (once)"
    S->>H: "resync-request"
    H->>S: "snapshot seq 5 tree"
    S->>C: "snapshot seq 5 tree"
    C->>C: "replace tree, clear flag"
```

Applying an out-of-order patch would corrupt the tree silently, so the
store skips it and asks once (no resync spam while the gap persists).
Duplicates and stale seqs are ignored without asking.

## Render pipeline

```mermaid
flowchart TD
    R["render_fn(state)"]
    E["expand components<br/>(hook slots by fn + key)"]
    G["prune unvisited slots"]
    Z["serialize callables<br/>to handlerId descriptors"]
    A["allowlist check"]
    T["strict double-render"]
    X["run effects"]
    F["diff_and_commit"]
    R --> E --> G --> Z --> A --> T --> X --> F
```

Expansion reuses the cached subtree of any memoised component rather than
running its body. Serialization replaces each callable with `{handlerId,
preventDefault, stopPropagation, throttleMs?}` and returns the node it was
given wherever nothing changed, so untouched subtrees keep their identity; a
memoised subtree reuses its serialized form too and replays its registry
entries, since the registry is rebuilt from nothing each render. There is no
deepcopy in this path — serialization used to mutate a copy of the whole tree,
which cost more than the diff it fed. The allowlist rejects unknown node types
on both ends (`__Slot__` exempt, `__Component__` never survives expansion).
Effects run once the tree is built, children before parents.

## Hook slots

```mermaid
flowchart TD
    C["component call<br/>Section key sec"]
    S["slot id is fn + key<br/>(or tree path)"]
    N["seen this render?"]
    N -- "no, first mount" --> I["init slots"]
    N -- "yes" --> R["reuse slots by call order"]
    I --> H["run body<br/>use_state, use_memo, use_effect"]
    R --> H
    H --> K["arity check"]
    K -- "same count" --> V["mark visited"]
    K -- "changed" --> ERR["RuntimeError"]
    V --> U["unvisited pruned<br/>at end of render"]
```

Keys follow reorders, positions behave React-like. The frame stack is
thread-local, so two Layouts driven from two threads cannot reach each other's
slots. Setters bail out on identical values and schedule that component's slot
alone rather than the whole layout, which is what makes per-component
memoisation possible; `use_memo` recomputes only on dep change (exotic values
recompute rather than lie). `use_effect` runs after the render commits and its
cleanup runs before the effect runs again and once when the component is
pruned. A reused subtree reports itself as still mounted, or the prune would
collect its hooks and the component would silently restart.

## Scheduling across hosts

```mermaid
flowchart TD
    subgraph K["tick host"]
        K1["invalidate per tick"]
        K2["flush state version"]
    end
    subgraph Y["async host"]
        Y1["invalidate on event"]
        Y2["await Driver run"]
    end
    subgraph N["naive host"]
        N1["invalidate + flush<br/>per message"]
    end
    K1 --> K2
    Y1 --> Y2
```

One `Driver` primitive serves all three: dirty flag + seq counter shared by
`flush()` (sync) and `run()` (async, bursts coalesce). The raw-ASGI adapter
(`create_ws_app`) is the async recipe with one session per connection.
