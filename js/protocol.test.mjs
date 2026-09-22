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
  createSlotHub,
  debounce,
  createChangeSender,
  createThrottledChangeSender,
  shouldPreventDefault,
  shouldStopPropagation,
  throttle,
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

test("policy helpers default safe for missing descriptors", () => {
  assert.equal(shouldPreventDefault(undefined), true);
  assert.equal(shouldPreventDefault({}), true);
  assert.equal(shouldPreventDefault({ preventDefault: false }), false);
  assert.equal(shouldStopPropagation(undefined), false);
  assert.equal(shouldStopPropagation({ stopPropagation: true }), true);
});

test("throttle sends leading immediately, trailing latest once", async () => {
  const calls = [];
  const fn = throttle((v) => calls.push(v), 20);
  fn("a");
  assert.deepEqual(calls, ["a"]);
  fn("b");
  fn("c");
  await new Promise((r) => setTimeout(r, 40));
  assert.deepEqual(calls, ["a", "c"]);
});

test("throttle trailing:false drops in-window repeats (double-submit guard)", async () => {
  const calls = [];
  const fn = throttle((v) => calls.push(v), 20, { trailing: false });
  fn("a");
  fn("b");
  await new Promise((r) => setTimeout(r, 40));
  assert.deepEqual(calls, ["a"]);
});

test("throttled change sender streams latest slider values", async () => {
  const sent = [];
  const sender = createThrottledChangeSender((m) => sent.push(m), 10);
  sender.send("0.2:on_change:s", 1);
  sender.send("0.2:on_change:s", 2);
  await new Promise((r) => setTimeout(r, 30));
  assert.equal(sent.length, 2); // leading 1 + trailing latest 2
  assert.equal(sent[1].event.value, 2);
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

test("slot hub remembers values and notifies by name", () => {
  const hub = createSlotHub();
  hub.set("rpm", 1200); // before anyone listens: kept, not lost
  assert.equal(hub.get("rpm"), 1200);

  const heard = [];
  const off = hub.subscribe("rpm", () => heard.push(hub.get("rpm")));
  hub.subscribe("temp", () => heard.push("temp"));
  hub.set("rpm", 1300);
  hub.set("rpm", 1300); // unchanged: no notify
  off();
  hub.set("rpm", 1400);
  assert.deepEqual(heard, [1300]);
});

test("slot hub replace notifies changed and removed names only", () => {
  const hub = createSlotHub();
  hub.set("a", 1);
  hub.set("b", 2);
  const heard = [];
  for (const n of ["a", "b", "c"]) hub.subscribe(n, () => heard.push(n));
  hub.replace({ a: 1, c: 3 });
  assert.deepEqual(heard.sort(), ["b", "c"]);
  assert.equal(hub.get("b"), undefined);
  assert.equal(hub.get("c"), 3);
});

test("applyOps shares every subtree an op does not touch", () => {
  // structuredClone of the whole tree per patch gave every node a new
  // identity, so nothing downstream could tell what had actually changed.
  const doc = {
    type: "Stack",
    children: [
      { type: "Text", props: { value: "a" } },
      { type: "Text", props: { value: "b" } },
    ],
    props: { gap: 1 },
  };
  const out = applyOps(doc, [{ op: "replace", path: "/children/1/props/value", value: "B" }]);

  assert.equal(out.children[1].props.value, "B");
  assert.equal(out.children[0], doc.children[0], "untouched sibling was copied");
  assert.equal(out.props, doc.props, "untouched props were copied");
  assert.notEqual(out.children, doc.children);
  assert.equal(doc.children[1].props.value, "b", "input was mutated");
});

test("applyOps applies several ops to one path without touching the input", () => {
  const doc = { children: [{ key: "a" }, { key: "b" }, { key: "c" }] };
  const frozen = structuredClone(doc);
  const out = applyOps(doc, [
    { op: "remove", path: "/children/1" },
    { op: "add", path: "/children/1", value: { key: "x" } },
    { op: "add", path: "/children/-", value: { key: "z" } },
  ]);
  assert.deepEqual(out.children.map((c) => c.key), ["a", "x", "c", "z"]);
  assert.equal(out.children[0], doc.children[0]);
  assert.deepEqual(doc, frozen);
});

test("applyOps copies an op's value, so the message can be reused", () => {
  const value = { props: { value: "v" } };
  const out = applyOps({}, [{ op: "add", path: "/n", value }]);
  value.props.value = "changed";
  assert.equal(out.n.props.value, "v");
});
