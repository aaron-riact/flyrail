import * as React from "react";
import { afterEach, expect, test } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createRenderer } from "./ServerNode.tsx";

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
