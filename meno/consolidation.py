"""The consolidation (dream) cycle: the circadian/low-load pass that bridges
hot → cold and keeps the graph healthy. Runs the gate LOOSE (redesign.md):
fold, recombine, reconsolidate, error-correct, forget, promote/demote.
"""
from __future__ import annotations

from typing import Dict

from .embeddings import cosine


class ConsolidationCycle:
    def __init__(self, mind) -> None:
        self.mind = mind

    def run(self) -> Dict[str, int]:
        g = self.mind.graph
        cfg = self.mind.cfg
        report = {"promoted": 0, "loose_links": 0, "reconsolidated": 0, "forgotten": 0}

        # 1+6. promote provisional nodes that earned reactivation (have edges);
        #      a provisional node is "committed" once it is woven in.
        for node in list(g.nodes.values()):
            if node.kind == "provisional" and any(True for _ in g.neighbors(node.id)):
                node.kind = "concept"
                node.salience = min(1.0, node.salience + 0.4)
                report["promoted"] += 1

        # 2. loose recombination — link similar nodes the greedy waking gate
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

        # 3. reconsolidation — re-reconstruct reflections against the evolved graph
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

        self.mind.trace(f"dream: {report}")
        return report
