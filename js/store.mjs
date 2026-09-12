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
    if (lastSeq === null) {
      tree = applyOps(tree ?? {}, msg.ops);
      lastSeq = msg.seq;
      emit({ kind: "patch" });
      return;
    }
    if (msg.seq <= lastSeq) return; // duplicate or stale: ignore
    if (msg.seq !== lastSeq + 1) {
      // Out-of-order apply would corrupt the tree: skip and ask for snapshot.
      if (!needsResync) {
        needsResync = true;
        emit({ kind: "resync-needed" });
        if (onResync) onResync(resyncRequestMessage());
      }
      return;
    }
    tree = applyOps(tree ?? {}, msg.ops);
    lastSeq = msg.seq;
    emit({ kind: "patch" });
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
