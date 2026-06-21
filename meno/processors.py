"""Processors: the typed, self-selecting handlers (system-design.md).

Each declares a cheap ``triggers`` predicate (self-selection — no processor calls
another) and a ``run`` action that may invoke a model and emits *commitment*
events. The trigger splits into relevance (intrinsic) and budget (extrinsic);
budget-fail defers rather than discards, which is where deferred impulses come
from. World-changing effects live only in the cognitive-tier Effector.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

from .event import Event, Kind, Status


class Processor:
    name = "processor"
    tier = 0

    def triggers(self, event: Event, mind) -> bool:
        return False

    def run(self, event: Event, mind) -> List[Event]:
        return []


class Appraiser(Processor):
    """Tier 1 — sensory appraisal: encode, route (already done by annotator),
    react, and emit a residual question if the event is surprising."""
    name = "appraiser"
    tier = 1

    # Only real percepts are encoded — afferent senses and effector feedback.
    # Derived cognition (SELF/STORAGE) flows and may climb, but is not each
    # turned into a node (that was the node-explosion bug). See decision D8.
    ENCODE = (Kind.SENSE, Kind.FEEDBACK)

    def triggers(self, event: Event, mind) -> bool:
        return self.name not in event.seen_by and event.kind in self.ENCODE

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        res = mind.models.appraise(event.content, event.surprise)
        # encode as a provisional node (forgetting has a front end: weak, decays).
        # The node lives in the GRAPH, so it must carry a COLD vector — not the
        # event's hot one (which is only for surprise/routing). add_node embeds
        # cold from content when no embedding is supplied (D20). With a single
        # embedder the two spaces coincide, so this is a no-op there.
        node = mind.graph.add_node(
            event.content, kind="provisional",
            salience=mind.cfg.provisional_salience,
            meta={"event": event.id, "stream": event.stream_id})
        event.node_id = node.id
        event.status = Status.PROVISIONAL
        event.depth_reached = max(event.depth_reached, 1)
        stream = mind.streams.get(event.stream_id)
        if stream is not None:
            if stream.node_ids:                       # Hebbian: chain to the stream's prior node
                mind.graph.link(stream.node_ids[-1], node.id, weight=mind.cfg.hebbian_increment)
            stream.node_ids.append(node.id)
        event.payload["reaction"] = res["reaction"]
        emitted: List[Event] = []
        q = res.get("question")
        # a residual question is a commitment that may climb — but only a percept
        # raises one, so questions never recursively spawn questions.
        if q and event.kind == Kind.SENSE:
            child = event.child(q, inherit=mind.cfg.activation_inherit, kind=Kind.SELF)
            child.payload["role"] = "question"
            emitted.append(child)
            # bottom-up curiosity: an unresolved question is a pull worth keeping (F3)
            mind.curiosities.register(q, source="bottom-up", stream_id=event.stream_id)
        return emitted


class Associator(Processor):
    """Tier 2 — find a connection in the graph and strengthen it."""
    name = "associator"
    tier = 2

    def triggers(self, event: Event, mind) -> bool:
        if self.name in event.seen_by or event.surprise < mind.cfg.tier2_min:
            return False
        stream = mind.streams.get(event.stream_id)
        return stream is not None and len(stream.node_ids) >= 2 and event.node_id is not None

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        stream = mind.streams.get(event.stream_id)
        own = set(stream.node_ids) if stream else set()
        emitted: List[Event] = []

        # (a) similarity — alike-but-not-yet-connected (cold retrieval). The probe
        # must be in COLD (graph) space to match the node vectors it scores against
        # — the event's hot embedding would be a different space under a split (D20).
        probe = mind.embed.embed_cold(event.content)
        for sim, nid in mind.graph.similar(probe, k=3, exclude=tuple(own)):
            if sim >= mind.cfg.tier2_min and event.node_id is not None:
                mind.graph.link(event.node_id, nid, weight=mind.cfg.hebbian_increment * sim)
                related = mind.graph.nodes[nid].content
                text = mind.models.associate(stream.summary if stream else event.content, [related])
                child = event.child(text, inherit=mind.cfg.activation_inherit)
                child.payload["role"] = "connection"
                child.depth_reached = 2
                emitted.append(child)
                break   # one good connection per pass; the child may climb further

        # (b) resonance — already-connected, via graph spreading activation (F7).
        # This is "the spine" used in cognition, not just inside reconstruct:
        # traversal finds what densely co-activates; similarity (above) finds the
        # alike-but-unlinked. They are complementary.
        if stream and stream.node_ids and event.node_id is not None:
            act = mind.graph.spread(stream.node_ids, hops=2, decay=0.5)
            resonant = sorted(((a, nid) for nid, a in act.items()
                               if nid not in own and nid in mind.graph.nodes),
                              reverse=True)
            if resonant:
                _, nid = resonant[0]
                mind.graph.link(event.node_id, nid, weight=mind.cfg.hebbian_increment * 0.5)

        event.depth_reached = max(event.depth_reached, 2)
        return emitted


class Synthesiser(Processor):
    """Tier 3 — synthesise a reflection from a stream and store it as a cue.
    Deep budget is scarce; relevant-but-unaffordable defers (builds pressure)."""
    name = "synthesiser"
    tier = 3

    def wants(self, event: Event, mind) -> bool:
        if self.name in event.seen_by:
            return False
        st = mind.streams.get(event.stream_id)
        if st is not None and st.refractory:       # F6: just synthesised — rest until the dream
            return False
        if event.payload.get("role") == "wake":    # a resurfaced deferred impulse always wants depth
            return True
        if st is None or len(st.node_ids) < 2:     # needs at least some material
            return False
        # Synthesis is earned by accumulated coherence OR by a single striking percept
        # — NOT by the latest event being novel (a coherent stream habituates, F5).
        return (len(st.node_ids) >= mind.cfg.synth_min_nodes
                or event.surprise >= mind.cfg.tier3_min)

    def triggers(self, event: Event, mind) -> bool:
        return self.wants(event, mind) and mind.deep_budget > 0

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        mind.deep_budget -= 1
        stream = mind.streams.get(event.stream_id)
        occasion = stream.summary if stream and stream.summary else event.content[:60]
        node_ids = list(stream.node_ids) if stream else ([event.node_id] if event.node_id else [])
        material = [mind.graph.nodes[n].content for n in node_ids if n in mind.graph.nodes][:6]
        text = mind.models.synthesise(occasion, material or [event.content])
        # Default is reconstructive — journaling is a separate, DELIBERATE act
        # (decision D10). Surprise is the wrong proxy: a novel percept is ~1.0.
        cue = mind.graph.store_cue(node_ids, occasion, tone=event.surprise,
                                   conclusion=text, journal=False)
        if stream is not None:
            stream.deferred = False
            stream.pressure = 0.0
            stream.refractory = True              # F6: rest until the next dream clears it
            stream.fatigue += mind.cfg.fatigue_gain
            mind.curiosities.satisfy(stream.id)  # F3: the reflection answers the stream's curiosities
        event.depth_reached = 3
        # storage-as-trigger: the act of forming a reflection re-enters the loop
        storage = event.child(f"reflection formed: {text}", inherit=mind.cfg.activation_inherit,
                              kind=Kind.STORAGE)
        storage.payload.update({"role": "reflection", "cue": cue.id})
        return [storage]


class Effector(Processor):
    """Cognitive-tier action on the world, with proprioceptive feedback. Only
    fires on explicit INTENT events — never reflexively (safety rule)."""
    name = "effector"
    tier = 2

    def triggers(self, event: Event, mind) -> bool:
        return event.kind == Kind.INTENT and event.payload.get("action") in ("fs_read", "fs_write")

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        action = event.payload["action"]
        rel = Path(event.payload.get("path", "")).name or "scratch.txt"
        target = mind.workspace / rel
        try:
            if action == "fs_write":
                target.write_text(event.payload.get("data", ""))
                result = f"wrote {len(event.payload.get('data', ''))} chars to {rel}"
            else:
                result = target.read_text() if target.exists() else f"(no such file: {rel})"
        except Exception as exc:   # feedback even on failure — an effector must not be blind
            result = f"action {action} failed: {exc}"
        fb = event.child(f"[{action} {rel}] {result}", inherit=mind.cfg.activation_inherit,
                         kind=Kind.FEEDBACK)
        fb.payload["role"] = "feedback"
        return [fb]


DEFAULT_PROCESSORS = [Appraiser(), Associator(), Synthesiser(), Effector()]
