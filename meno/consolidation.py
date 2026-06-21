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
        report = {"promoted": 0, "loose_links": 0, "merges": 0,
                  "rediscovered": 0, "reconsolidated": 0, "forgotten": 0}

        # 1+6. promote provisional nodes that earned reactivation (have edges);
        #      a provisional node is "committed" once it is woven in.
        for node in list(g.nodes.values()):
            if node.kind == "provisional" and any(True for _ in g.neighbors(node.id)):
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
        for a_id, b_id in sm.detect_merge():
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

        # 4. reconsolidation — re-reconstruct reflections against the evolved graph
        for cue in list(g.cues.values()):
            if cue.verbatim is None and any(n in g.nodes for n in cue.entry_points):
                g.reconstruct(cue, self.mind.models)
                report["reconsolidated"] += 1

        # 5. forgetting — edges decay before nodes (islanding)
        g.decay()

        # 6b. drop provisional nodes that never earned their keep
        for nid, node in list(g.nodes.items()):
            if node.kind == "provisional" and node.salience < cfg.edge_prune_floor:
                del g.nodes[nid]
                report["forgotten"] += 1

        # F6: a new dream lifts the refractory hold, so streams can think again
        for s in list(sm.active.values()) + list(sm.warm.values()):
            s.refractory = False

        self.mind.trace(f"dream: {report}")
        return report
