// Pure wire-protocol helpers for the flyrail renderer.
// No React, no MUI: unit-testable with `node --test` and imported by
// ServerNode.tsx so the tested code IS the shipped code.

export function actionMessage(handlerId, event) {
  const msg = { chan: "ui", type: "action", handlerId };
  if (event !== undefined) msg.event = event;
  return msg;
}

export function changeMessage(handlerId, value) {
  return actionMessage(handlerId, { value });
}

export function slotMessage(name, value) {
  return { chan: "ui", type: "slot", name, value };
}

export function patchMessage(ops, seq) {
  return { chan: "ui", type: "patch", seq, ops };
}

export function childKey(node, index) {
  // Stable item ids survive reorders; index fallback only for keyless nodes.
  if (typeof node === "string") return index;
  return node?.key ?? index;
}

export function isKnownComponent(registry, type) {
  // `import * as MUI` also exports non-components (colors, createTheme);
  // only functions are renderable, which doubles as an allowlist check.
  return typeof registry?.[type] === "function";
}

export function normalizeButtonProps(props, isButton) {
  // Python API says label=, MUI Button renders children.
  const out = { ...(props || {}) };
  if (isButton && out.label !== undefined && out.children === undefined) {
    out.children = out.label;
    delete out.label;
  }
  return out;
}

export function debounce(fn, waitMs) {
  // Trailing-edge only: keystrokes coalesce, the last value always sends.
  let timer = null;
  let lastArgs = null;
  function debounced(...args) {
    lastArgs = args;
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      timer = null;
      fn(...lastArgs);
    }, waitMs);
  }
  debounced.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  debounced.flush = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
      fn(...lastArgs);
    }
  };
  return debounced;
}

export function createChangeSender(send, waitMs = 150) {
  // One instance per input node (see ServerNode): coalescing is keyed by
  // call order, so sharing one across fields would clobber concurrent edits.
  const debounced = debounce((hid, value) => send(changeMessage(hid, value)), waitMs);
  return {
    send: (hid, value) => debounced(hid, value),
    flush: () => debounced.flush(),
    cancel: () => debounced.cancel(),
  };
}

export function createThrottledChangeSender(send, waitMs) {
  // Slider-style inputs: intermediate values matter, but not at 60Hz.
  // Leading call sends immediately, later calls collapse to the trailing latest.
  const throttled = throttle((hid, value) => send(changeMessage(hid, value)), waitMs);
  return {
    send: (hid, value) => throttled(hid, value),
    flush: () => throttled.flush(),
    cancel: () => throttled.cancel(),
  };
}

export function shouldPreventDefault(entry) {
  // Policy mirror of Layout.EVENT_DEFAULTS: a socket-driven control never
  // triggers browser navigation unless the descriptor explicitly opts out.
  // Applied synchronously in the React handler (a debounced callback can no
  // longer cancel the event) and defaults safe for hand-built trees.
  return entry?.preventDefault !== false;
}

export function shouldStopPropagation(entry) {
  return entry?.stopPropagation === true;
}

export function throttle(fn, waitMs, { trailing = true } = {}) {
  let lastCall = 0;
  let timer = null;
  let lastArgs = null;
  function throttled(...args) {
    const now = Date.now();
    const remaining = waitMs - (now - lastCall);
    lastArgs = args;
    if (remaining <= 0) {
      if (timer) {
        clearTimeout(timer);
        timer = null;
      }
      lastCall = now;
      fn(...args);
    } else if (trailing && !timer) {
      timer = setTimeout(() => {
        timer = null;
        lastCall = Date.now();
        fn(...lastArgs);
      }, remaining);
    }
  }
  throttled.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
  };
  throttled.flush = () => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
      lastCall = Date.now();
      fn(...lastArgs);
    }
  };
  return throttled;
}

export function parsePointer(path) {
  // RFC6901 with our convention: "" and "/" both address the document root.
  if (path === "" || path === "/") return [];
  if (!path.startsWith("/")) throw new Error(`invalid pointer ${JSON.stringify(path)}`);
  return path
    .slice(1)
    .split("/")
    .map((seg) => seg.replace(/~1/g, "/").replace(/~0/g, "~"));
}

function parentOf(doc, segments) {
  let node = doc;
  for (const seg of segments) {
    if (node === null || typeof node !== "object") {
      throw new Error("pointer traverses a scalar");
    }
    node = Array.isArray(node) ? node[Number(seg)] : node[seg];
  }
  return node;
}

function setKey(container, key, value, create) {
  if (Array.isArray(container)) {
    if (key === "-") {
      if (!create) throw new Error("'-' only valid for add");
      container.push(value);
      return;
    }
    const i = Number(key);
    if (!Number.isInteger(i) || i < 0 || i > container.length - (create ? 0 : 1)) {
      throw new Error(`array index out of bounds: ${JSON.stringify(key)}`);
    }
    if (create) container.splice(i, 0, value);
    else container[i] = value;
    return;
  }
  if (create && !(key in container)) {
    // add: new key; replace: must exist (strict, surfaces skew loudly)
  } else if (!create && !(key in container)) {
    throw new Error(`missing key ${JSON.stringify(key)}`);
  }
  container[key] = value;
}

export function applyOps(doc, ops) {
  // Applies the RFC6902 subset Layout emits (add/replace/remove). Returns a
  // new document; the input is deep-cloned, never mutated (React state safe).
  // Only understands what _diff produces: dict recursion plus wholesale
  // array replacement, but array indices are handled for robustness.
  let out = structuredClone(doc);
  for (const op of ops ?? []) {
    const segments = parsePointer(op.path ?? "");
    if (segments.length === 0) {
      if (op.op === "remove") {
        out = {};
      } else {
        out = structuredClone(op.value);
      }
      continue;
    }
    const parent = parentOf(out, segments.slice(0, -1));
    const key = segments[segments.length - 1];
    if (op.op === "remove") {
      if (Array.isArray(parent)) parent.splice(Number(key), 1);
      else delete parent[key];
    } else if (op.op === "add") {
      setKey(parent, key, structuredClone(op.value), true);
    } else if (op.op === "replace") {
      setKey(parent, key, structuredClone(op.value), false);
    } else {
      throw new Error(`unsupported op ${JSON.stringify(op.op)}`);
    }
  }
  return out;
}

export function createSlotHub() {
  // Last value per slot name, plus listeners per name. Remembering the value
  // is the point: a SlotView that mounts after its value arrived must still
  // show it, and a store and a renderer can share one hub.
  const values = new Map();
  const listeners = new Map();

  function notify(name) {
    listeners.get(name)?.forEach((fn) => fn());
  }

  return {
    get: (name) => values.get(name),
    set(name, value) {
      if (values.has(name) && Object.is(values.get(name), value)) return;
      values.set(name, value);
      notify(name);
    },
    replace(entries) {
      // A snapshot: exactly these slots now, telling only the names that moved.
      const next = new Map(Object.entries(entries ?? {}));
      const moved = [];
      for (const name of values.keys()) if (!next.has(name)) moved.push(name);
      for (const [name, value] of next) {
        if (!values.has(name) || !Object.is(values.get(name), value)) moved.push(name);
      }
      values.clear();
      for (const [name, value] of next) values.set(name, value);
      moved.forEach(notify);
    },
    subscribe(name, fn) {
      if (!listeners.has(name)) listeners.set(name, new Set());
      listeners.get(name).add(fn);
      return () => listeners.get(name)?.delete(fn);
    },
  };
}
