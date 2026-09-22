// Framework-free client store for flyrail trees.
// Ingests the multiplexed {chan:"ui"} messages (patch/slot/snapshot),
// tracks seq for gap detection, and notifies subscribers. React binding
// is a thin useSyncExternalStore wrapper (see ServerNode docs); all logic
// here is unit-tested with `node --test`.
import { applyOps } from "./protocol.mjs";

export function resyncRequestMessage() {
  return { chan: "ui", type: "resync-request" };
}

export function createStore(options = {}) {
  const { onResync } = options;
  let tree = null;
  let lastSeq = null;
  let needsResync = false;
  const slots = new Map();
  const listeners = new Set();

  function emit(kind) {
    listeners.forEach((fn) => fn(kind));
  }

  function ingestPatch(msg) {
    if (typeof msg.seq !== "number") throw new Error("patch without seq");
    // No baseline yet reads as seq 0: the server's first patch is seq 1 and
    // a diff against {}, so it applies; any later one is a diff against a
    // tree this client never had, which is just a gap.
    const base = lastSeq ?? 0;
    if (msg.seq <= base) return; // duplicate or stale: ignore
    if (msg.seq !== base + 1) {
      // Out-of-order apply would corrupt the tree: skip and ask for snapshot.
      requestResync();
      return;
    }
    let next;
    try {
      next = applyOps(tree ?? {}, msg.ops);
    } catch {
      // The ops do not fit the tree we hold, so the two have drifted apart.
      // Throwing would leave every later patch to fail the same way.
      requestResync();
      return;
    }
    tree = next;
    lastSeq = msg.seq;
    emit({ kind: "patch" });
  }

  function requestResync() {
    if (needsResync) return;
    needsResync = true;
    emit({ kind: "resync-needed" });
    if (onResync) onResync(resyncRequestMessage());
  }

  function ingest(msg) {
    if (!msg || msg.chan !== "ui") return;
    if (msg.type === "patch") ingestPatch(msg);
    else if (msg.type === "slot") {
      slots.set(msg.name, msg.value);
      emit({ kind: "slot" });
    } else if (msg.type === "snapshot") {
      tree = structuredClone(msg.tree ?? {});
      slots.clear();
      for (const [k, v] of Object.entries(msg.slots ?? {})) slots.set(k, v);
      if (typeof msg.seq === "number") lastSeq = msg.seq;
      needsResync = false;
      emit({ kind: "snapshot" });
    }
    // Unknown ui subtypes are ignored: forward-compat with future message kinds.
  }

  return {
    ingest,
    getTree: () => tree,
    getSlot: (name) => slots.get(name),
    getSeq: () => lastSeq,
    doesNeedResync: () => needsResync,
    subscribe: (fn) => {
      listeners.add(fn);
      return () => listeners.delete(fn);
    },
  };
}
