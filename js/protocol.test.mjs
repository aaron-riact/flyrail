import { test } from "node:test";
import assert from "node:assert/strict";
import {
  actionMessage,
  changeMessage,
  slotMessage,
  patchMessage,
  childKey,
  isKnownComponent,
  normalizeButtonProps,
} from "./protocol.mjs";

test("click action omits event when absent", () => {
  assert.deepEqual(actionMessage("0.0:on_click:"), {
    chan: "ui",
    type: "action",
    handlerId: "0.0:on_click:",
  });
});

test("change action wraps input value", () => {
  assert.deepEqual(changeMessage("0.1:on_change:k1", "a@b.c"), {
    chan: "ui",
    type: "action",
    handlerId: "0.1:on_change:k1",
    event: { value: "a@b.c" },
  });
});

test("slot and patch envelopes multiplex on chan=ui", () => {
  assert.equal(slotMessage("rows", [1]).chan, "ui");
  const patch = patchMessage([{ op: "replace", path: "/children", value: [] }], 7);
  assert.equal(patch.seq, 7);
  assert.equal(patch.ops.length, 1);
});

test("childKey prefers stable key, falls back to index", () => {
  assert.equal(childKey({ key: "a1" }, 0), "a1");
  assert.equal(childKey({}, 3), 3);
  assert.equal(childKey("text", 2), 2);
  assert.equal(childKey(null, 5), 5);
});

test("registry lookup rejects non-components", () => {
  const registry = { Button: () => {}, colors: { red: 1 }, version: "6" };
  assert.equal(isKnownComponent(registry, "Button"), true);
  assert.equal(isKnownComponent(registry, "colors"), false);
  assert.equal(isKnownComponent(registry, "Missing"), false);
});

test("label folds into children for buttons only", () => {
  assert.deepEqual(normalizeButtonProps({ label: "Save" }, true), { children: "Save" });
  assert.deepEqual(normalizeButtonProps({ label: "L" }, false), { label: "L" });
  // Explicit children win; never clobber.
  assert.deepEqual(
    normalizeButtonProps({ label: "L", children: "C" }, true),
    { label: "L", children: "C" },
  );
});
