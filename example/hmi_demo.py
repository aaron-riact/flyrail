"""Best-practices demo: fixed-tick server loop with a scripted client.

Run:  PYTHONPATH=. python3 example/hmi_demo.py

Narrates the wire exactly as your app would speak it: seq-numbered patch
envelopes on change, silence on idle ticks, actions routed by handlerId,
slot fast-path for hot values, snapshot recovery after a dropped patch.
The client half (apply, seq tracking, resync) is the JS store in
js/store.mjs; here the scripted client just prints what it would do.
"""
from pyforms import Layout, Stack, Text, Button, TextField
from pyforms.transport import ui_envelope_patch


class Sim:
    def __init__(self):
        self.speed = 10
        self.name = "rig-1"
        self.items = [{"id": "a1", "name": "box A"}, {"id": "a2", "name": "box B"}]


class Panel:
    def render(self, s):
        return Stack(
            Text(f"{s.name}: {s.speed}"),
            Button("Stop", on_click=self.stop),
            TextField(value=s.name, on_change=self.rename, key="name"),
            Stack(*[Text(i["name"], key=i["id"]) for i in s.items], key="items"),
        )

    def stop(self, state, event):
        state.speed = 0

    def rename(self, state, event):
        state.name = event["value"]


def main():
    s = Sim()
    layout = Layout(
        Panel().render, allowed_types={"Stack", "Text", "Button", "TextField"}
    )
    seq = 0
    sent = 0

    def tick(n):
        nonlocal seq, sent
        ops = layout.tick(s)  # BEST PRACTICE: single render+diff per tick
        if not ops:
            print(f"[tick {n:02d}] silent (tree unchanged)")
            return
        seq += 1  # BEST PRACTICE: caller-owned seq; only bump on send
        sent += 1
        env = ui_envelope_patch(ops, seq)
        print(f"[tick {n:02d}] -> patch seq={env['seq']} ops={len(ops)}")

    def act(suffix, event=None):
        hid = next(h for h in layout.registry if h.endswith(suffix))
        layout.dispatch(hid, s, event)
        print(f"[client] action {suffix} event={event}")

    tick(0)  # initial full patch
    tick(1)  # idle: silent
    tick(2)  # idle: silent
    act(":on_click:")  # Stop button
    tick(3)  # speed 10 -> 0: patch
    act(":on_change:name", {"value": "rig-2"})  # rename input (debounced client-side)
    s.items.reverse()  # reorder: stable keys, one replace op
    tick(4)

    # Hot path: 60Hz telemetry bypasses the tree diff entirely.
    for frame in range(3):
        msg = layout.set_slot("rows", [frame, frame + 1])
        if msg:
            sent += 1
            print(f"[tick hot] -> slot rows={msg['value']}")
    assert layout.set_slot("rows", [2, 3]) is None, "repeat slot must be silent"

    # Dropped patch: client would send resync-request; answer with snapshot.
    snap = layout.snapshot(s, seq=seq + 1)
    seq += 1
    sent += 1
    print(f"[server] -> snapshot seq={snap['seq']} (gap recovery)")
    tick(5)  # baseline continues from the snapshot: silent

    print(f"done: {sent} wire messages; registry={len(layout.registry)} handlers")
    assert sent == 7, sent  # 3 patches + 3 slots + 1 snapshot


if __name__ == "__main__":
    main()
