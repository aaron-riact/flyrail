"""Optional FastAPI helper. Skip it if you have your own socket/tick."""
from __future__ import annotations
from typing import Any


def ui_envelope_patch(ops: list, seq: int) -> dict:
    return {"chan": "ui", "type": "patch", "seq": seq, "ops": ops}


FASTAPI_EXAMPLE = '''
# tick integration sketch (your loop owns timing):
from pyforms import Layout
layout = Layout(MyPanel().render, allowed_types={"Stack","Text","Button","TextField"})
seq = 0
def on_tick(state):
    global seq
    ops = layout.tick(state)  # [] when unchanged
    if ops:
        seq += 1
        broadcast(ui_envelope_patch(ops, seq))

# your existing ws handler:
async def on_ws_msg(msg, state):
    if msg.get("chan") == "ui" and msg.get("type") == "action":
        layout.dispatch(msg["handlerId"], state, msg.get("event"))
'''
