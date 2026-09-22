import { test } from "node:test";
import assert from "node:assert/strict";
import { createStore, resyncRequestMessage } from "./store.mjs";

function patch(seq, ops) {
  return { chan: "ui", type: "patch", seq, ops };
}

test("patches apply in order and advance seq", () => {
  const store = createStore();
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  store.ingest(patch(2, [{ op: "add", path: "/b", value: 2 }]));
  assert.deepEqual(store.getTree(), { a: 1, b: 2 });
  assert.equal(store.getSeq(), 2);
});

test("duplicates and stale patches are ignored", () => {
  const store = createStore();
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  store.ingest(patch(1, [{ op: "add", path: "/b", value: 99 }]));
  store.ingest(patch(0, [{ op: "add", path: "/c", value: 99 }]));
  assert.deepEqual(store.getTree(), { a: 1 });
});

test("seq gap skips apply and fires resync once", () => {
  const sent = [];
  const store = createStore({ onResync: (m) => sent.push(m) });
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  store.ingest(patch(3, [{ op: "add", path: "/evil", value: true }]));
  assert.equal(store.doesNeedResync(), true);
  assert.deepEqual(store.getTree(), { a: 1 }); // gap patch NOT applied
  assert.deepEqual(sent, [resyncRequestMessage()]);
  store.ingest(patch(4, [{ op: "add", path: "/evil", value: true }]));
  assert.equal(sent.length, 1); // no resync spam while gap persists
});

test("snapshot recovers from a gap", () => {
  const store = createStore();
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  store.ingest(patch(3, [{ op: "add", path: "/evil", value: true }]));
  assert.equal(store.doesNeedResync(), true);
  store.ingest({ chan: "ui", type: "snapshot", seq: 3, tree: { a: 1, b: 2 } });
  assert.equal(store.doesNeedResync(), false);
  assert.deepEqual(store.getTree(), { a: 1, b: 2 });
  assert.equal(store.getSeq(), 3);
});

test("slots bypass the tree and non-ui traffic is ignored", () => {
  const store = createStore();
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  store.ingest({ chan: "ui", type: "slot", name: "rows", value: [1, 2] });
  assert.deepEqual(store.getSlot("rows"), [1, 2]);
  assert.deepEqual(store.getTree(), { a: 1 });
  store.ingest({ chan: "telemetry", speed: 42 });
  assert.deepEqual(store.getTree(), { a: 1 });
});

test("subscribers are notified and can unsubscribe", () => {
  const store = createStore();
  const kinds = [];
  const unsub = store.subscribe((k) => kinds.push(k.kind));
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  unsub();
  store.ingest(patch(2, [{ op: "add", path: "/b", value: 2 }]));
  assert.deepEqual(kinds, ["patch"]);
});

test("a client joining mid-stream asks for a snapshot instead of patching nothing", () => {
  // A patch is a diff against a tree this client never had. Applied to {},
  // a replace throws, lastSeq stays null, and every later patch throws too.
  const sent = [];
  const store = createStore({ onResync: (m) => sent.push(m) });
  store.ingest(patch(5, [{ op: "replace", path: "/props/value", value: "x" }]));
  assert.equal(store.doesNeedResync(), true);
  assert.equal(store.getTree(), null);
  assert.deepEqual(sent, [resyncRequestMessage()]);
  store.ingest({ chan: "ui", type: "snapshot", seq: 6, tree: { a: 1 } });
  store.ingest(patch(7, [{ op: "add", path: "/b", value: 2 }]));
  assert.deepEqual(store.getTree(), { a: 1, b: 2 });
});

test("a patch that does not fit the tree asks for a snapshot instead of throwing", () => {
  const sent = [];
  const store = createStore({ onResync: (m) => sent.push(m) });
  store.ingest(patch(1, [{ op: "add", path: "/a", value: 1 }]));
  store.ingest(patch(2, [{ op: "replace", path: "/missing/x", value: 2 }]));
  assert.deepEqual(store.getTree(), { a: 1 });
  assert.equal(store.doesNeedResync(), true);
  assert.deepEqual(sent, [resyncRequestMessage()]);
});

test("store slots live in a hub a renderer can share", () => {
  const store = createStore();
  const heard = [];
  store.slots.subscribe("rpm", () => heard.push(store.slots.get("rpm")));
  store.ingest({ chan: "ui", type: "slot", name: "rpm", value: 1200 });
  store.ingest({ chan: "ui", type: "snapshot", seq: 2, tree: {}, slots: { rpm: 900 } });
  assert.deepEqual(heard, [1200, 900]);
  assert.equal(store.getSlot("rpm"), 900);
});
