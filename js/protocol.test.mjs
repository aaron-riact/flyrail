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
  applyOps,
  parsePointer,
  debounce,
  createChangeSender,
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

test("debounce coalesces rapid calls into the latest", async () => {
  const calls = [];
  const fn = debounce((v) => calls.push(v), 10);
  fn("a");
  fn("b");
  fn("c");
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(calls, ["c"]);
});

test("debounce flush sends pending immediately, cancel drops it", async () => {
  const calls = [];
  const fn = debounce((v) => calls.push(v), 20);
  fn("a");
  fn.flush();
  assert.deepEqual(calls, ["a"]);
  fn("b");
  fn.cancel();
  await new Promise((r) => setTimeout(r, 40));
  assert.deepEqual(calls, ["a"]);
});

test("change sender wraps debounced input values", async () => {
  const sent = [];
  const sender = createChangeSender((m) => sent.push(m), 10);
  sender.send("0.1:on_change:k1", "h");
  sender.send("0.1:on_change:k1", "hi");
  await new Promise((r) => setTimeout(r, 30));
  assert.deepEqual(sent, [
    {
      chan: "ui",
      type: "action",
      handlerId: "0.1:on_change:k1",
      event: { value: "hi" },
    },
  ]);
});

test("pointer unescapes ~0/~1 and addresses root", () => {
  assert.deepEqual(parsePointer(""), []);
  assert.deepEqual(parsePointer("/"), []);
  assert.deepEqual(parsePointer("/a~1b/~0c"), ["a/b", "~c"]);
});

test("applyOps replaces wholesale arrays like Layout emits", () => {
  const doc = { type: "Stack", children: [{ type: "Text", key: "a" }] };
  const out = applyOps(doc, [
    { op: "replace", path: "/children", value: [{ type: "Text", key: "b" }] },
  ]);
  assert.deepEqual(out.children, [{ type: "Text", key: "b" }]);
  // Input untouched (React state safety).
  assert.deepEqual(doc.children, [{ type: "Text", key: "a" }]);
});

test("applyOps handles add/remove on dicts", () => {
  const out = applyOps({ a: 1 }, [
    { op: "add", path: "/b", value: 2 },
    { op: "remove", path: "/a" },
  ]);
  assert.deepEqual(out, { b: 2 });
});

test("applyOps replaces the root document", () => {
  assert.deepEqual(applyOps({ a: 1 }, [{ op: "replace", path: "", value: { b: 2 } }]), { b: 2 });
});

test("applyOps rejects unknown ops and skew loudly", () => {
  assert.throws(() => applyOps({}, [{ op: "move", path: "/a" }]), /unsupported op/);
  assert.throws(() => applyOps({}, [{ op: "replace", path: "/missing", value: 1 }]), /missing key/);
});
