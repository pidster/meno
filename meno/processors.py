"""Processors: the typed, self-selecting handlers (system-design.md).

Each declares a cheap ``triggers`` predicate (self-selection — no processor calls
another) and a ``run`` action that may invoke a model and emits *commitment*
events. The trigger splits into relevance (intrinsic) and budget (extrinsic);
budget-fail defers rather than discards, which is where deferred impulses come
from. World-changing effects live only in the cognitive-tier Effector.
"""
from __future__ import annotations

import queue
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
        # a tripped cost governor (D32) withholds Tier-3 too — the want defers (below),
        # building pressure, and resumes when the throttle lifts. Not discarded. A FORCED
        # wake (D33 fixation take-up) is the one exception: an impulse starved past the TTL
        # is taken up even while throttled, so it can finally discharge instead of looping.
        if not (self.wants(event, mind) and mind.deep_budget > 0):
            return False
        return (not mind.throttled) or bool(event.payload.get("forced"))

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        mind.deep_budget -= 1
        mind.cost_units += 1                        # Tier-3 synthesis: a deep op (D32)
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
            stream.deferred_ticks = 0             # genuinely discharged: the fixation clock resets (D33)
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
                  "what is a ", "what is ", "what are ", "what does ", "define ",
                  "definition of ", "the definition of ", "meaning of ",
                  "a synonym for ", "synonym for "):
        if term.startswith(frame):
            term = term[len(frame):]
            break
    # strip a trailing 'mean'/'means'/'defined' tail so 'what does X mean' -> X (so a
    # later 'what is X' resolves to the SAME def: key — a repeat lookup must be a hit)
    term = term.strip().strip("?.!").strip()
    for tail in (" mean", " means", " mean?", " defined", " explained"):
        if term.endswith(tail):
            term = term[: -len(tail)].strip()
            break
    if term:
        cands += [f"def:{term}", f"syn:{term}", term]
        last = term.split()[-1] if term.split() else ""
        if last and last != term:                  # a single-token repeat of a multi-word term
            cands.append(f"def:{last}")
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
        cannot contaminate the identity substrate (K2). On a Library MISS it falls
        through to an external network authority (K3): an outbound, egress-gated
        knowledge intent the KnowledgeAdapter resolves off-thread, curating the result
        back into the Library so a repeat is a local hit. With no authority configured,
        the driver feeds back an honest miss."""
        query = event.payload.get("key") or event.payload.get("term") or event.payload.get("query", "")
        candidates = library_key_candidates(query)
        for key in candidates:
            ref = mind.library.get(key)
            if ref is not None:
                out = event.child(ref.body, inherit=mind.cfg.activation_inherit,
                                  kind=Kind.REFERENCE, source="reference")
                out.payload.update({"role": "reference", "action": None, "key": ref.key,
                                    "hit": True, "provenance": f"reference:{ref.key}",
                                    "external": True})
                return [out]
        # K3: miss -> route OUTWARD to a network authority (if one is configured).
        curate_key = next((c for c in candidates if c.startswith("def:")),
                          candidates[0] if candidates else query)
        intent = event.child(f"intent: knowledge {query}", inherit=mind.cfg.activation_inherit,
                             kind=Kind.INTENT, source="curiosity")
        intent.payload.update({"action": "knowledge", "key": query,
                               "curate_key": curate_key, "egress": True})
        return [intent]


class OutboundRelay(Processor):
    """The efferent hand-off (I0a). An INTENT explicitly marked `egress=True` is
    *outbound* — destined for an integration adapter (a channel, a network authority),
    set by whatever emits it (I2's effector). Rather than run it on the mind thread
    (where a network call would block all of cognition), the relay enqueues it to the
    bounded `outbox` and returns immediately; a Driver worker drains the outbox
    OFF-thread. The marker is closed-world ON PURPOSE: a local action (fs_read, lookup,
    a future tool) is NOT egress, so it is never mis-relayed-and-dropped — only an
    intent that declares itself outward is handed off."""
    name = "outbound_relay"
    tier = 2

    def triggers(self, event: Event, mind) -> bool:
        return (event.kind == Kind.INTENT
                and self.name not in event.seen_by
                and bool(event.payload.get("egress"))
                and getattr(mind, "outbox", None) is not None)

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        try:                                  # bounded: drop newest if the outbox is full
            mind.outbox.put_nowait(dict(event.payload))
        except queue.Full:
            mind.outbox_drops += 1            # observed, never silent (R2 dropped-input precedent)
        return []                             # the adapter feeds the result back, async


class Curator(Processor):
    """K3: curate a looked-up fact into the self's Library, on the mind thread. A
    network authority result re-enters as a REFERENCE tagged `curate=True`; the Curator
    retains it (D25 'decide to retain') so a repeat lookup is a LOCAL hit — the agent
    learns what it looked up. The same REFERENCE is appraised-but-not-encoded by the
    Appraiser, so it informs cognition without contaminating the substrate. Running
    here (a kernel processor on the mind thread) keeps Library writes off the worker
    thread that fetched the fact."""
    name = "curator"
    tier = 1

    def triggers(self, event: Event, mind) -> bool:
        return (event.kind == Kind.REFERENCE and self.name not in event.seen_by
                and bool(event.payload.get("curate")) and bool(event.payload.get("key"))
                and getattr(mind, "library", None) is not None)

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        from .library import Reference
        try:
            mind.library.put(Reference(key=event.payload["key"], body=event.content,
                                       source=event.payload.get("provenance", "lookup:authority"),
                                       kind="reference"))
        except Exception:                             # a malformed result is not retained; never fatal
            pass
        return []


class Engagement(Processor):
    """I3: react to being ADDRESSED. Meno MAY turn toward an interlocutor and reply — it
    is not a chatbot, so it weighs whether it has something earned to say and may stay
    SILENT. A reply is an outward POST intent through the gated effector; the may-not-must
    restraint, the cost governor (it withholds while throttled), and the rate limit keep
    it from being a chatterbox. Responding emerges from sensing — being addressed is a
    salient percept it chooses to act on, not a request it is obliged to answer."""
    name = "engagement"
    tier = 2

    def triggers(self, event: Event, mind) -> bool:
        return (self.name not in event.seen_by
                and event.payload.get("addressed") in ("directed", "possibly")
                and bool(event.payload.get("reply_to"))
                and not getattr(mind, "throttled", False)
                and getattr(mind, "engage_budget", 0) > 0     # bound the per-cycle reply burst
                and getattr(mind, "outbox", None) is not None)

    def run(self, event: Event, mind) -> List[Event]:
        event.seen_by.add(self.name)
        mind.engage_budget -= 1                          # spend a reply slot BEFORE the model call
        rt = event.payload.get("reply_to") or {}
        msg = event.content                              # strip the 'slack #chan: ' percept prefix
        prefix = f"slack #{rt.get('channel')}: "
        if msg.startswith(prefix):
            msg = msg[len(prefix):]
        recalled = mind.recall(msg)                      # substrate-first: what do I actually know?
        decision = mind.models.respond({
            "name": getattr(mind, "name", "meno"),
            "addressed": event.payload["addressed"],
            "text": msg, "actor": rt.get("user"),
            "memory": (recalled or {}).get("text", "")})
        mind.cost_units += 1                             # a respond judgment is a deep op (D32)
        if not isinstance(decision, dict) or not decision.get("speak") or not decision.get("text"):
            mind.trace(f"engagement: stayed silent on {msg[:40]!r}")
            return []                                    # chose silence — may-not-must
        intent = Event(content=f"reply to {rt.get('user')}: {decision['text'][:60]}",
                       kind=Kind.INTENT, source="engagement",
                       payload={"action": "post", "channel": rt.get("channel"),
                                "thread_ts": rt.get("thread_ts"), "text": decision["text"],
                                "egress": True, "host": "slack.com"})
        return [intent]


DEFAULT_PROCESSORS = [Appraiser(), Associator(), Synthesiser(), Engagement(),
                      Effector(), OutboundRelay(), Curator()]
