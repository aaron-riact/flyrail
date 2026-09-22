import * as React from 'react';
import {
  createChangeSender,
  createThrottledChangeSender,
  shouldPreventDefault,
  shouldStopPropagation,
  throttle,
  actionMessage,
  childKey,
  isKnownComponent,
  normalizeButtonProps,
  createSlotHub,
} from './protocol.mjs';

/**
 * BYOF renderer. Auto-registers MUI (or any lib) — no switch statement.
 *
 *   import * as MUI from '@mui/material';
 *   import { createRenderer } from 'flyrail-renderer/react';
 *   const { ServerNode, setSlot } = createRenderer({ ...MUI });
 *
 * Pass the store's slots so slot and snapshot messages reach SlotView:
 *
 *   createRenderer({ ...MUI }, { slots: store.slots });
 *
 * Wire logic (message shapes, key resolution, label folding) lives in
 * protocol.mjs and is unit-tested with `node --test`; this file only
 * binds it to React.
 */
export function createRenderer(
  registry: Record<string, any>,
  { slots = createSlotHub() }: { slots?: ReturnType<typeof createSlotHub> } = {},
) {
  // One hub per renderer unless shared, so two mounted trees cannot
  // cross-talk. It remembers values, so a SlotView that mounts after its
  // value arrived still shows it.
  function setSlot(name: string, value: any) {
    slots.set(name, value);
  }

  function SlotView({ name, fallback }: { name: string; fallback?: any }) {
    const subscribe = React.useCallback(
      (onChange: () => void) => slots.subscribe(name, onChange),
      [name],
    );
    const v = React.useSyncExternalStore(subscribe, () => slots.get(name));
    return <>{v ?? fallback}</>;
  }

  function ServerNode({ node, send }: { node: any; send: (msg: any) => void }) {
    // First line, before any early return: hooks must run unconditionally.
    const senderRef = React.useRef<{
      key: string;
      api: ReturnType<typeof createChangeSender>;
    } | null>(null);
    const clickRef = React.useRef<{
      key: string;
      send: () => void;
      cancel: () => void;
    } | null>(null);
    // What the user typed and the server has not echoed yet. The server's
    // value controls the input, and a change goes out only after the
    // debounce, so without this every keystroke was put back.
    const [draft, setDraft] = React.useState<{ hid: string; value: any } | null>(null);
    const serverValue = node?.props?.value;
    React.useEffect(() => {
      // Caught up: hand control back, so a later server change shows.
      if (draft && Object.is(draft.value, serverValue)) setDraft(null);
    }, [draft, serverValue]);
    if (!node) return null;
    if (node.type === '__Slot__') {
      return <SlotView name={node.props.name} fallback={node.props.default} />;
    }
    if (!isKnownComponent(registry, node.type)) return null;
    const Comp = registry[node.type];
    const props: any = normalizeButtonProps(node.props, Comp === registry['Button']);
    // python on_click/on_change -> react onClick/onChange carrying handlerId
    if (node.on_click) {
      const entry = node.on_click;
      const hid = entry.handlerId;
      const t = entry.throttleMs;
      // Optional leading-edge throttle doubles as a double-submit guard.
      const key = `${hid}|${t ?? "direct"}`;
      if (!clickRef.current || clickRef.current.key !== key) {
        clickRef.current?.cancel();
        const sendNow = () => send(actionMessage(hid));
        const gated =
          typeof t === "number" ? throttle(sendNow, t, { trailing: false }) : sendNow;
        clickRef.current = {
          key,
          send: gated,
          cancel: () => (gated as { cancel?: () => void }).cancel?.(),
        };
      }
      props.onClick = (e: any) => {
        if (shouldPreventDefault(entry)) e.preventDefault();
        if (shouldStopPropagation(entry)) e.stopPropagation();
        clickRef.current!.send();
      };
    }
    if (node.on_change) {
      const entry = node.on_change;
      const hid = entry.handlerId;
      const t = entry.throttleMs;
      // One sender per input: sharing across fields would let concurrent
      // edits clobber each other. Recreate on handlerId or mode change
      // (list reorder) so strokes never route to a stale row. Sliders opt
      // into throttleMs; everything else keeps the 150ms debounce.
      const key = `${hid}|${t ?? "debounce"}`;
      if (!senderRef.current || senderRef.current.key !== key) {
        senderRef.current?.api.cancel();
        const api =
          typeof t === "number"
            ? createThrottledChangeSender(send, t)
            : createChangeSender(send);
        senderRef.current = { key, api };
      }
      const api = senderRef.current.api;
      const controlled = 'value' in (node.props || {});
      if (controlled && draft && draft.hid === hid && !Object.is(draft.value, serverValue)) {
        props.value = draft.value;
      }
      props.onChange = (e: any) => {
        if (shouldPreventDefault(entry)) e.preventDefault();
        if (shouldStopPropagation(entry)) e.stopPropagation();
        const value = e?.target?.value;
        if (controlled) setDraft({ hid, value });
        api.send(hid, value);
      };
    }
    // No server children: leave props.children alone. Passing an empty list
    // as JSX children overrides the prop, which blanked every Button label.
    if (!node.children?.length) return <Comp {...props} />;
    const children = node.children.map((c: any, i: number) => {
      if (typeof c === 'string') return <React.Fragment key={i}>{c}</React.Fragment>;
      // stable keys: key comes from python `key=` (item id, never index-derived)
      return <ServerNode key={childKey(c, i)} node={c} send={send} />;
    });
    return <Comp {...props}>{children}</Comp>;
  }

  return { ServerNode, setSlot, slots };
}
