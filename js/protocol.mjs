// Pure wire-protocol helpers for the pyforms renderer.
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
