"""The consolidation (dream) cycle: the circadian/low-load pass that bridges
hot → cold and keeps the graph healthy. Runs the gate LOOSE (redesign.md):
fold, recombine, reconsolidate, error-correct, forget, promote/demote.
"""
from __future__ import annotations

from typing import Dict

from .embeddings import cosine
from .event import Event, Kind


class ConsolidationCycle:
    def __init__(self, mind) -> None:
        self.mind = mind

    def run(self) -> Dict[str, int]:
        g = self.mind.graph
        cfg = self.mind.cfg
        sm = self.mind.streams
        report = {"promoted": 0, "loose_links": 0, "merges": 0, "rediscovered": 0,
                  "reconsolidated": 0, "forgotten": 0, "retired": 0, "pruned": 0}

        # 1+6. promote provisional nodes that earned reactivation (have edges);
        #      a provisional node is "committed" once it is woven in. Build the
        #      "has an edge" set once (O(edges)) rather than scanning neighbours per
        #      node (O(nodes*edges)) — the dream blocks the live loop (R3 review P1).
        edged = set()
        for a, b in g.edges:
            edged.add(a)
            edged.add(b)
        for node in list(g.nodes.values()):
            if node.kind == "provisional" and node.id in edged:
                node.kind = "concept"
                node.salience = min(1.0, node.salience + 0.4)
                report["promoted"] += 1

        # 2. rediscovery — runs BEFORE loose recombination, while islanded nodes
        #    are still islanded: a recently-added node bridges to an islanded one
        #    it resembles, recovering it "via a path that did not exist when it
        #    was lost". Wires the formerly-dead similar()/islanded(). F4.
        recent = sorted(g.nodes)[-cfg.dream_recombine_window:]
        rcap = cfg.rediscovery_cap
        for nid in recent:
            if rcap <= 0:
                break
            for sim, other in g.similar(g.nodes[nid].embedding, k=3, exclude=(nid,)):
                if sim >= cfg.rediscovery_threshold and g.islanded(other):
                    g.link(nid, other, weight=cfg.hebbian_increment)
                    report["rediscovered"] += 1
                    rcap -= 1
                    # storage-as-trigger: the recovered memory re-enters on the bus
                    self.mind.bus.publish(Event(
                        content=f"rediscovered: {g.nodes[other].content}",
                        kind=Kind.STORAGE, source="dream"))
                    break

        # 3. loose recombination — link similar nodes the greedy waking gate
        #    skipped. Bounded to the most-recent window and a hard cap so the
        #    dream can't explode (decision D9).
        ids = sorted(g.nodes)[-cfg.dream_recombine_window:]
        budget = cfg.dream_recombine_cap
        for i in range(len(ids)):
            if budget <= 0:
                break
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                key = (min(a, b), max(a, b))
                if key in g.edges:
                    continue
                if cosine(g.nodes[a].embedding, g.nodes[b].embedding) >= cfg.loose_link_sim:
                    g.link(a, b, weight=0.3)
                    report["loose_links"] += 1
                    budget -= 1
                    if budget <= 0:
                        break

        # 2b. merge — convergent streams become one (insight). Candidates come
        #     from cheap centroid cosine; the DECISION to merge is the model's
        #     (relate), and a confirmed merge synthesises over the union = the aha. F2.
        #     EXPENSIVE (two model calls per merge) — skipped while throttled (D32): the
        #     cheap forgetting passes still run, so the dream keeps the graph healthy even
        #     when the cost governor has withheld the generative work.
        for a_id, b_id in (() if self.mind.throttled else sm.detect_merge()):
            a, b = sm.active.get(a_id), sm.active.get(b_id)
            if not a or not b:
                continue
            if self.mind.models.relate(a.summary, b.summary):
                merged = sm.merge(a_id, b_id)
                if merged is None:
                    continue
                s = sm.active[merged]
                s.refractory = False
                material = [g.nodes[n].content for n in s.node_ids if n in g.nodes][:6]
                synth_material = material or [s.summary]
                text = self.mind.models.synthesise(f"insight: {s.summary}", synth_material)
                g.store_cue(s.node_ids, f"insight: {s.summary}", tone=0.9,
                            conclusion=text, material=synth_material)
                report["merges"] += 1

        # 4. reconsolidation — re-reconstruct reflections against the evolved graph.
        #    BOUNDED to the most relevant cues (D19/A3): re-reconstructing EVERY cue
        #    each dream is O(lifetime) and, with a real model, one expensive call per
        #    cue. Rank by recall then recency and take the cap; the rest keep their
        #    gist (still recallable) until something brings them back.
        live = [c for c in g.cues.values()
                if c.verbatim is None and any(n in g.nodes for n in c.entry_points)]
        live.sort(key=lambda c: (c.recalls, c.created_at), reverse=True)
        for cue in (live[:cfg.reconsolidate_cap] if not self.mind.throttled else []):
            g.reconstruct(cue, self.mind.models)        # a model call per cue — skip while throttled
            report["reconsolidated"] += 1

        # 5. forgetting — edges decay before nodes (islanding)
        g.decay()

        # 6b. drop provisional nodes that never earned their keep
        for nid, node in list(g.nodes.items()):
            if node.kind == "provisional" and node.salience < cfg.edge_prune_floor:
                del g.nodes[nid]
                report["forgotten"] += 1

        # 4b. reflection forgetting — the SAME tiered descent nodes get (doc 01 §3),
        #     not a GC sweep (R3 review). A reflection whose anchors have all islanded
        #     or vanished is a GHOST: available but inaccessible ("I know I concluded
        #     something here"). A ghost is first offered REDISCOVERY — a recent,
        #     semantically-similar memory re-recognises its gist and re-anchors it,
        #     recovered "by a route that did not exist when it was lost". Only a ghost
        #     that stays unrecovered and unrecalled for cue_ghost_ttl dreams is finally
        #     RELEASED — and the agent reflects on the loss (grief), it isn't collected.
        recent_nodes = [g.nodes[nid] for nid in sorted(g.nodes)[-cfg.dream_recombine_window:]]
        # which nodes still have an edge (post-decay) — computed once so the ghost
        # check is O(cues * entry_points), not O(cues * edges) via islanded() (R3 P1).
        edged_now = set()
        for a, b in g.edges:
            edged_now.add(a)
            edged_now.add(b)
        grieved = 0
        for cue in list(g.cues.values()):
            if cue.verbatim is not None or cue.recalls > 0:
                cue.ghost_ticks = 0                         # journaled or recalled: anchored to the self
                continue
            if any(n in g.nodes and n in edged_now for n in cue.entry_points):
                cue.ghost_ticks = 0                         # still has a living, connected anchor
                continue
            # a ghost: try to rediscover it via gist recognition by a recent memory
            recovered = False
            for node in recent_nodes:
                if node.id in cue.entry_points:
                    continue
                if g.recognise(cue, node.embedding) >= cfg.rediscovery_threshold:
                    cue.entry_points = (list(cue.entry_points) + [node.id])[-cfg.stream_material_window:]
                    cue.ghost_ticks = 0
                    report["rediscovered"] += 1
                    self.mind.trace(f"a memory re-surfaced reflection {cue.id}: {cue.occasion[:40]!r}")
                    recovered = True
                    break
            if recovered:
                continue
            cue.ghost_ticks += 1
            if cue.ghost_ticks >= cfg.cue_ghost_ttl and grieved < cfg.cue_retire_max_per_dream:
                # release (grief): the agent registers the loss as a reflection of its
                # own — a memory of having let go, not a silent delete with a log line.
                # Under throttle the reflection is templated (no model call) but still
                # journaled — grief stays deliberate and durable, just not model-authored.
                if self.mind.throttled:
                    loss = f"a conclusion once reached about {cue.occasion[:40]}, now released"
                else:
                    loss = self.mind.models.synthesise(
                        f"letting go of a reflection about {cue.occasion[:40]}",
                        [f"a conclusion once reached about {cue.occasion[:40]}, now beyond recall"])
                del g.cues[cue.id]
                # journal the grief: a DURABLE, recallable memory of having let go (so
                # it's a real reflection the agent can read back, not a gist-only
                # ghost) — and journaled cues are exempt from the ghost path, so the
                # act of grieving doesn't itself become an endless grief-about-grief.
                g.store_cue([], f"released: {cue.occasion[:40]}", tone=0.3,
                            conclusion=loss, material=[cue.occasion], journal=True)
                grieved += 1
                report["retired"] += 1
                self.mind.trace(f"released reflection {cue.id} after {cue.ghost_ticks} silent dreams")

        # 6c. substrate ceiling (D33): a hard cap on node count. Overflow is NOT garbage-
        #     collected — whole islanded node-streams are RELEASED with grief, the node
        #     analogue of cue retirement above. The agent reflects on letting a body of
        #     memory go and journals that reflection (durable, recallable); it never silent-
        #     -deletes. Bounded per dream (drains gradually); whole streams only (never
        #     split a train of thought); live and deliberately-journaled memory is spared.
        if cfg.node_ceiling and len(g.nodes) > cfg.node_ceiling:
            # "live" = actually being thought about (has working-set events) or an unfinished
            # impulse (deferred) — NOT merely lingering in `active`/`warm`. A dormant,
            # consolidated stream IS prunable; a mid-thought or still-pushing one is not.
            live_streams = {e.stream_id for e in self.mind.working_set.events.values()
                            if e.stream_id is not None}
            live_streams |= {sid for sid, s in list(sm.active.items()) + list(sm.warm.items())
                             if s.deferred}
            # spare the anchors of memory the agent deliberately keeps: journaled cues AND
            # actively-recalled reflections (recalls > 0) — the same "anchored to the self"
            # that the cue-grief path (4b) spares. Don't hollow a live reflection to a ghost.
            protected = {n for c in g.cues.values()
                         if c.verbatim is not None or c.recalls > 0
                         for n in c.entry_points}
            # group nodes into WHOLE streams. A node with no stream tag is NOT pruned (an
            # orphan must not be culled one-by-one — that would split, the GC-creep the
            # ethos forbids); orphans persist until they earn a stream or decay normally.
            cohorts: Dict[object, list] = {}
            for nid, node in g.nodes.items():
                skey = node.meta.get("stream")
                if skey is not None:
                    cohorts.setdefault(skey, []).append(nid)

            def _value(members):                                # lower = more releasable
                sal = sum(g.nodes[m].salience for m in members) # faint memory goes first...
                deg = sum(1 for (a, b) in g.edges if a in members or b in members)  # ...and islanded
                return (sal + deg, min(members))                # tie-break: oldest cohort first

            candidates = sorted(
                ((k, m) for k, m in cohorts.items()
                 if k not in live_streams and not any(x in protected for x in m)),
                key=lambda km: _value(km[1]))
            released = 0
            for key, members in candidates:
                if len(g.nodes) <= cfg.node_ceiling or released >= cfg.node_grief_max_per_dream:
                    break
                occasion = g.nodes[members[0]].content[:40]
                if self.mind.throttled:                        # cheap mode: no model call while
                    loss = f"released {len(members)} memories around {occasion} to stay within myself"
                else:
                    loss = self.mind.models.synthesise(
                        f"letting go of {len(members)} memories around {occasion}",
                        [f"a body of {len(members)} memories about {occasion}, released to stay within myself"])
                    self.mind.cost_units += 1                  # a grief synthesis is a deep op (D32)
                dead = set(members)
                for m in members:
                    del g.nodes[m]
                for ekey in [e for e in g.edges if e[0] in dead or e[1] in dead]:
                    del g.edges[ekey]                           # no dangling edges into the void
                g.store_cue([], f"released {len(members)} memories: {occasion}", tone=0.3,
                            conclusion=loss, material=[occasion], journal=True)
                released += 1
                report["pruned"] += len(members)
                self.mind.trace(f"grief-pruned a {len(members)}-node stream at the ceiling: {occasion!r}")

        # F6: a new dream lifts the refractory hold, so streams can think again
        for s in list(sm.active.values()) + list(sm.warm.values()):
            s.refractory = False

        self.mind.trace(f"dream: {report}")
        return report
