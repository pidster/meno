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

    # The appraiser APPRAISES (reacts to) afferent senses, effector feedback, AND
    # looked-up references — so a reference informs the moment's cognition. But it
    # only ENCODES (turns into a graph node) senses and feedback. A REFERENCE is read
    # and NOT encoded (K2): reference is not experience, so it must never become a
    # node in the identity substrate. Derived cognition (SELF/STORAGE) flows and may
    # climb, but is not each turned into a node either (the node-explosion bug, D8).
    APPRAISE = (Kind.SENSE, Kind.FEEDBACK, Kind.REFERENCE)
    ENCODE = (Kind.SENSE, Kind.FEEDBACK)

    def triggers(self, event: Event, mind) -> bool:
        return self.name not in event.seen_by and event.kind in self.APPRAISE

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        res = mind.models.appraise(event.content, event.surprise)
        if event.kind in self.ENCODE:
            # encode as a provisional node (forgetting has a front end: weak, decays).
            # The node lives in the GRAPH, so it must carry a COLD vector — not the
            # event's hot one (which is only for surprise/routing). add_node embeds
            # cold from content when no embedding is supplied (D20). With a single
            # embedder the two spaces coincide, so this is a no-op there.
            node = mind.graph.add_node(
                event.content, kind="provisional",
                salience=mind.cfg.provisional_salience,
                # carry PROVENANCE: where this memory came from. World-sensed content
                # (source != self/cognition) must be distinguishable from the agent's own
                # thought, so the self-graph isn't quietly contaminated by ingested text.
                meta={"event": event.id, "stream": event.stream_id,
                      "source": event.source, "external": event.kind == Kind.SENSE})
            event.node_id = node.id
            event.status = Status.PROVISIONAL
            stream = mind.streams.get(event.stream_id)
            if stream is not None:
                if stream.node_ids:                   # Hebbian: chain to the stream's prior node
                    mind.graph.link(stream.node_ids[-1], node.id, weight=mind.cfg.hebbian_increment)
                stream.node_ids.append(node.id)
                w = mind.cfg.stream_material_window   # window the id list (D19 int-list bound)
                if len(stream.node_ids) > w:
                    stream.node_ids = stream.node_ids[-w:]
        # A reference is appraised but left UNENCODED: no node, so the Associator
        # (which needs event.node_id) won't weave it into the graph and synthesise
        # won't draw it as material — it informs this moment, then is gone unless the
        # self deliberately curates it into the Library (D25).
        event.depth_reached = max(event.depth_reached, 1)
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
        synth_material = material or [event.content]
        text = mind.models.synthesise(occasion, synth_material)
        # Default is reconstructive — journaling is a separate, DELIBERATE act
        # (decision D10). Surprise is the wrong proxy: a novel percept is ~1.0.
        cue = mind.graph.store_cue(node_ids, occasion, tone=event.surprise,
                                   conclusion=text, journal=False, material=synth_material)
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


def library_key_candidates(query: str) -> List[str]:
    """Normalise a curiosity/term into candidate exact Library keys. This is the
    curiosity-text -> key bridge (K2's likeliest failure point): the Library is
    exact-key, so a natural-language curiosity ('what is the definition of entropy')
    must be reduced to a key the shelf actually holds ('def:entropy'). Tries the raw
    string and a namespaced/stemmed term, most-specific first."""
    raw = (query or "").strip()
    low = raw.lower()
    cands = [raw, low]
    # strip a leading question frame, keep the salient term
    term = low
    for frame in ("what is the definition of ", "what is the meaning of ",
                  "what is a ", "what is ", "what does ", "define ", "definition of ",
                  "the definition of ", "meaning of ", "a synonym for ", "synonym for "):
        if term.startswith(frame):
            term = term[len(frame):]
            break
    term = term.strip().strip("?.!").strip()
    if term:
        cands += [f"def:{term}", f"syn:{term}", term]
    # de-dup, preserve order
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c); out.append(c)
    return out


class Effector(Processor):
    """Cognitive-tier action, with proprioceptive feedback. Only fires on explicit
    INTENT events — never reflexively (safety rule). Filesystem actions act on the
    world and feed back as FEEDBACK (encoded as experience); a `lookup` resolves a
    fact against the self's Library and re-enters it as a REFERENCE (read, NOT
    encoded — K2: reference is not experience)."""
    name = "effector"
    tier = 2
    _FS = ("fs_read", "fs_write")
    _LOOKUP = ("lookup", "define")

    def triggers(self, event: Event, mind) -> bool:
        return (event.kind == Kind.INTENT
                and event.payload.get("action") in self._FS + self._LOOKUP)

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        action = event.payload["action"]
        if action in self._LOOKUP:
            return self._lookup(action, event, mind)
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

    def _lookup(self, action: str, event: Event, mind) -> List[Event]:
        """Resolve a fact against the self's Library (exact-key, K1) and re-enter it
        as a REFERENCE. The result informs cognition but is never encoded as a node
        (the Appraiser appraises REFERENCE without encoding it) — so a looked-up fact
        cannot contaminate the identity substrate (K2). K3 will fall through to a
        network authority on a miss; here a miss is just an honest miss."""
        query = event.payload.get("key") or event.payload.get("term") or event.payload.get("query", "")
        ref = None
        for key in library_key_candidates(query):
            ref = mind.library.get(key)
            if ref is not None:
                break
        if ref is not None:
            body, src = ref.body, f"reference:{ref.key}"
        else:
            body, src = f"(no reference for {query!r})", "reference:miss"
        out = event.child(body, inherit=mind.cfg.activation_inherit,
                          kind=Kind.REFERENCE, source="reference")
        out.payload.update({"role": "reference", "action": None,
                            "key": ref.key if ref else None, "hit": ref is not None,
                            "provenance": src, "external": True})
        return [out]


DEFAULT_PROCESSORS = [Appraiser(), Associator(), Synthesiser(), Effector()]
