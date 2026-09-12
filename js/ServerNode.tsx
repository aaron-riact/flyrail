import * as React from 'react';
import {
  createChangeSender,
  actionMessage,
  childKey,
  isKnownComponent,
  normalizeButtonProps,
} from './protocol.mjs';

/**
 * BYOF renderer. Auto-registers MUI (or any lib) — no switch statement.
 *
 *   import * as MUI from '@mui/material';
 *   import { createRenderer } from 'flyrail-renderer';
 *   const { ServerNode, setSlot } = createRenderer({ ...MUI });
 *
 * Wire logic (message shapes, key resolution, label folding) lives in
 * protocol.mjs and is unit-tested with `node --test`; this file only
 * binds it to React.
 */
export function createRenderer(registry: Record<string, any>) {
  // Slot store is per-renderer so two mounted trees cannot cross-talk.
  const slotListeners = new Map<string, Set<(v: any) => void>>();

  function setSlot(name: string, value: any) {
    slotListeners.get(name)?.forEach((fn) => fn(value));
  }

  function SlotView({ name, fallback }: { name: string; fallback?: any }) {
    const [v, setV] = React.useState(fallback);
    React.useEffect(() => {
      const fn = (nv: any) => setV(nv);
      if (!slotListeners.has(name)) slotListeners.set(name, new Set());
      slotListeners.get(name)!.add(fn);
      return () => {
        slotListeners.get(name)?.delete(fn);
      };
    }, [name]);
    return <>{v ?? fallback}</>;
  }

  function ServerNode({ node, send }: { node: any; send: (msg: any) => void }) {
    // First line, before any early return: hooks must run unconditionally.
    const senderRef = React.useRef<{
      hid: string;
      sender: ReturnType<typeof createChangeSender>;
    } | null>(null);
    if (!node) return null;
    if (node.type === '__Slot__') {
      return <SlotView name={node.props.name} fallback={node.props.default} />;
    }
    if (!isKnownComponent(registry, node.type)) return null;
    const Comp = registry[node.type];
    const props: any = normalizeButtonProps(node.props, Comp === registry['Button']);
    // python on_click/on_change -> react onClick/onChange carrying handlerId
    if (node.on_click) {
      const hid = node.on_click.handlerId;
      props.onClick = () => send(actionMessage(hid));
    }
    if (node.on_change) {
      const hid = node.on_change.handlerId;
      // One debounced sender per input: sharing across fields would let
      // concurrent edits clobber each other. Recreate on handlerId change
      // (list reorder) so strokes never route to a stale row.
      if (!senderRef.current || senderRef.current.hid !== hid) {
        senderRef.current?.sender.cancel();
        senderRef.current = { hid, sender: createChangeSender(send) };
      }
      const sender = senderRef.current.sender;
      props.onChange = (e: any) => sender.send(hid, e?.target?.value);
    }
    const children = (node.children || []).map((c: any, i: number) => {
      if (typeof c === 'string') return <React.Fragment key={i}>{c}</React.Fragment>;
      // stable keys: key comes from python `key=` (item id, never index-derived)
      return <ServerNode key={childKey(c, i)} node={c} send={send} />;
    });
    return <Comp {...props}>{children}</Comp>;
  }

  return { ServerNode, setSlot };
}
