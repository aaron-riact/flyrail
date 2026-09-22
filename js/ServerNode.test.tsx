import * as React from "react";
import { afterEach, expect, test, vi } from "vitest";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRenderer } from "./ServerNode.tsx";
import { createStore } from "./store.mjs";
import { applyOps } from "./protocol.mjs";

afterEach(cleanup);

// Stand-ins for MUI: plain elements that take the same props.
function Stack({ children }: any) {
  return <div>{children}</div>;
}
function Text({ value }: any) {
  return <span>{value}</span>;
}
function Button({ children, onClick }: any) {
  return <button onClick={onClick}>{children}</button>;
}
function TextField({ value, onChange }: any) {
  return <input aria-label="field" value={value ?? ""} onChange={onChange} />;
}
export const registry = { Stack, Text, Button, TextField };

test("renders a tree and sends a click as an action", () => {
  const { ServerNode } = createRenderer(registry);
  const sent: any[] = [];
  const tree = {
    type: "Stack",
    props: {},
    children: [
      { type: "Text", props: { value: "speed 3" } },
      { type: "Button", props: { label: "Stop" }, on_click: { handlerId: "h1" } },
    ],
  };
  render(<ServerNode node={tree} send={(m) => sent.push(m)} />);

  expect(screen.getByText("speed 3")).toBeTruthy();
  fireEvent.click(screen.getByRole("button"));
  expect(sent).toEqual([{ chan: "ui", type: "action", handlerId: "h1" }]);
});

test("a Button shows its label", () => {
  // normalizeButtonProps moves label= into props.children, but the node's
  // own (empty) children were passed as JSX children too, which win over the
  // prop -- so every Button rendered blank.
  const { ServerNode } = createRenderer(registry);
  render(
    <ServerNode
      node={{ type: "Button", props: { label: "Stop" }, on_click: { handlerId: "h1" } }}
      send={() => {}}
    />,
  );
  expect(screen.getByRole("button").textContent).toBe("Stop");
});

test("server children still render inside a component", () => {
  const { ServerNode } = createRenderer(registry);
  render(
    <ServerNode
      node={{ type: "Stack", props: {}, children: ["plain", { type: "Text", props: { value: "t" } }] }}
      send={() => {}}
    />,
  );
  expect(document.body.textContent).toBe("plaint");
});

const slotNode = { type: "__Slot__", props: { name: "rpm", default: "--" } };

test("a slot value set before the SlotView mounts is shown", () => {
  // setSlot only told current listeners, so a value that arrived before the
  // SlotView mounted was dropped and the default showed until the next one.
  const { ServerNode, setSlot } = createRenderer(registry);
  setSlot("rpm", 1200);
  render(<ServerNode node={slotNode} send={() => {}} />);
  expect(document.body.textContent).toBe("1200");
});

test("slots reach SlotView through a shared store, snapshots included", () => {
  const store = createStore();
  const { ServerNode } = createRenderer(registry, { slots: store.slots });
  render(<ServerNode node={slotNode} send={() => {}} />);
  expect(document.body.textContent).toBe("--");

  act(() => store.ingest({ chan: "ui", type: "slot", name: "rpm", value: 1200 }));
  expect(document.body.textContent).toBe("1200");

  act(() => store.ingest({ chan: "ui", type: "snapshot", seq: 1, tree: {}, slots: { rpm: 900 } }));
  expect(document.body.textContent).toBe("900");
});

function field(value: string, handlerId = "f1") {
  return { type: "TextField", props: { value }, on_change: { handlerId } };
}

test("typing into a server-valued field shows what was typed", () => {
  // The input is controlled by the server's value, and the change only goes
  // out after a 150ms debounce. Until the echo came back, React put the
  // server's old value back after every keystroke.
  vi.useFakeTimers();
  try {
    const { ServerNode } = createRenderer(registry);
    const sent: any[] = [];
    render(<ServerNode node={field("rig-1")} send={(m) => sent.push(m)} />);
    const input = screen.getByLabelText("field") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "rig-12" } });
    expect(input.value).toBe("rig-12");
    fireEvent.change(input, { target: { value: "rig-123" } });
    expect(input.value).toBe("rig-123");

    act(() => vi.advanceTimersByTime(200));
    expect(sent).toEqual([
      { chan: "ui", type: "action", handlerId: "f1", event: { value: "rig-123" } },
    ]);
  } finally {
    vi.useRealTimers();
  }
});

test("a stale echo does not overwrite newer typing", () => {
  const { ServerNode } = createRenderer(registry);
  const { rerender } = render(<ServerNode node={field("")} send={() => {}} />);
  const input = screen.getByLabelText("field") as HTMLInputElement;

  fireEvent.change(input, { target: { value: "abc" } });
  rerender(<ServerNode node={field("ab")} send={() => {}} />); // echo of an older value
  expect(input.value).toBe("abc");
});

test("once the server has caught up, its later changes show", () => {
  const { ServerNode } = createRenderer(registry);
  const { rerender } = render(<ServerNode node={field("")} send={() => {}} />);
  const input = screen.getByLabelText("field") as HTMLInputElement;

  fireEvent.change(input, { target: { value: "abc" } });
  rerender(<ServerNode node={field("abc")} send={() => {}} />); // echo caught up
  rerender(<ServerNode node={field("")} send={() => {}} />); // server clears it
  expect(input.value).toBe("");
});

test("a change still pending when the input unmounts is sent at once", () => {
  // The debounce timer outlived the component: the edit went out whenever it
  // fired, after the field was gone, or was lost if the page moved on.
  vi.useFakeTimers();
  try {
    const { ServerNode } = createRenderer(registry);
    const sent: any[] = [];
    const { unmount } = render(<ServerNode node={field("")} send={(m) => sent.push(m)} />);
    fireEvent.change(screen.getByLabelText("field"), { target: { value: "last words" } });

    unmount();
    expect(sent).toEqual([
      { chan: "ui", type: "action", handlerId: "f1", event: { value: "last words" } },
    ]);
    act(() => vi.advanceTimersByTime(200));
    expect(sent.length).toBe(1); // flushed once, not again by the old timer
  } finally {
    vi.useRealTimers();
  }
});

test("a patch re-renders only the nodes it changed", () => {
  // applyOps shares untouched subtrees, so a node whose object is the same
  // as last time has nothing new to show and should not render again.
  const renders: Record<string, number> = {};
  function Counted({ value }: any) {
    renders[value] = (renders[value] ?? 0) + 1;
    return <span>{value}</span>;
  }
  const { ServerNode } = createRenderer({ ...registry, Counted });
  const send = () => {};
  const before = {
    type: "Stack",
    props: {},
    children: [
      { type: "Counted", key: "a", props: { value: "a" } },
      { type: "Counted", key: "b", props: { value: "b" } },
    ],
  };
  const { rerender } = render(<ServerNode node={before} send={send} />);
  const after = applyOps(before, [{ op: "replace", path: "/children/1/props/value", value: "B" }]);
  rerender(<ServerNode node={after} send={send} />);

  expect(renders).toEqual({ a: 1, b: 1, B: 1 });
});
