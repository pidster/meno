"""The runtime: wires every component into one mind and drives the loop.

The deterministic core is synchronous and step-driven (`run_until_quiescent`) so
behaviour is reproducible and the scoring constants are tunable (decision D7). A
live async/threaded driver for real sensors is a thin wrapper to add later; the
kernel only requires *bounded* concurrency, which the worker-budget models.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from .annotator import Annotator
from .bus import Bus
from .config import Config
from .consolidation import ConsolidationCycle
from .control import Controller
from .embeddings import EmbeddingModel, HashingEmbedding, cosine
from .event import Event, Kind, Status
from .graph import Graph
from .models import ModelProvider, StubModelProvider
from .processors import DEFAULT_PROCESSORS, Synthesiser
from .streams import StreamManager
from .working_set import WorkingSet


class Meno:
    def __init__(self, config: Optional[Config] = None,
                 embed: Optional[EmbeddingModel] = None,
                 models: Optional[ModelProvider] = None,
                 processors: Optional[list] = None,
                 workspace: Optional[Path] = None,
                 verbose: bool = False) -> None:
        self.cfg = config or Config()
        self.embed = embed or HashingEmbedding()
        self.models = models or StubModelProvider()
        self.graph = Graph(self.embed, self.cfg)
        self.streams = StreamManager(self.embed, self.cfg)
        self.working_set = WorkingSet(self.cfg, self.streams)
        self.annotator = Annotator(self.embed, self.working_set, self.streams, self.cfg)
        self.bus = Bus()
        self.consolidation = ConsolidationCycle(self)
        self.controller = Controller(self)
        self.processors = processors or DEFAULT_PROCESSORS
        self.workspace = Path(workspace or ".meno_workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self.deep_budget = self.cfg.deep_per_pass
        self.traces: List[str] = []
        self._synth = next((p for p in self.processors if isinstance(p, Synthesiser)), None)

    # --- tracing ---
    def trace(self, msg: str) -> None:
        self.traces.append(msg)
        if self.verbose:
            print(f"  · {msg}")

    # --- input ---
    def feed(self, text: str, source: str = "chat", **payload) -> Event:
        ev = Event(content=text, kind=Kind.SENSE, source=source, payload=payload)
        self.bus.publish(ev)
        return ev

    def submit(self, event: Event) -> Event:
        self.bus.publish(event)
        return event

    # --- the gate at ingress: discard (habituate) or admit ---
    def _ingest(self) -> None:
        for ev in self.bus.drain():
            self.annotator.annotate(ev)
            if self.annotator.passes(ev):
                self.working_set.admit(ev)
            else:
                ev.status = Status.LAPSED
                self.trace(f"habituated (gate): {ev.content[:40]!r}")

    # --- one worker step: claim the top event and run matching processors ---
    def _process(self, ev: Event) -> None:
        emitted: List[Event] = []
        for proc in sorted(self.processors, key=lambda p: p.tier):
            if proc.triggers(ev, self):
                emitted.extend(proc.run(ev, self))
                self.trace(f"{proc.name}(t{proc.tier}) on {ev.content[:36]!r}")
        # relevance-but-unaffordable -> defer (build pressure), do not discard
        if self._synth and self._synth.wants(ev, self) and self.deep_budget <= 0:
            st = self.streams.get(ev.stream_id)
            if st is not None and not st.deferred:
                st.deferred = True
                self.trace(f"deferred (deep budget spent) -> stream {ev.stream_id}")
        for child in emitted:
            self.bus.publish(child)
        if ev.status == Status.ACTIVE:
            ev.status = Status.COMMITTED

    def run_until_quiescent(self) -> int:
        """Drain the current burst until the working set and bus go quiet.

        No interoceptive wakes fire here — reactive processing only. Initiative
        (resurfacing deferred impulses) is the heartbeat's job, between bursts.
        Returns steps taken."""
        steps = 0
        while steps < self.cfg.max_steps:
            self._ingest()
            ev = self.working_set.claim()
            if ev is None:
                if not self.bus.pending():
                    break                            # quiescent
                continue
            self._process(ev)
            steps += 1
        return steps

    def heartbeat(self, ticks: int = 8) -> int:
        """The quiet phase: build pressure on deferred streams, resurface them as
        interoceptive wakes (each granted a deep slot), and let initiative work
        through the backlog. This is where deep thought deferred during waking
        actually happens."""
        total = 0
        for _ in range(ticks):
            wakes = self.controller.tick()
            for w in wakes:
                self.bus.publish(w)
            total += self.run_until_quiescent()
            deferred_left = (any(s.deferred for s in self.streams.active.values())
                             or any(s.deferred for s in self.streams.warm.values()))
            if not wakes and not deferred_left:
                break
        return total

    # --- circadian: the dream ---
    def dream(self) -> dict:
        report = self.consolidation.run()
        self.deep_budget = self.cfg.deep_per_pass   # rested: deep capacity replenished
        return report

    # --- tiered recall (reconstructive reflection) ---
    def recall(self, query: str) -> dict:
        probe = self.embed.embed(query)
        best, best_sim = None, 0.0
        for cue in self.graph.cues.values():
            sim = self.graph.recognise(cue, probe)
            if sim > best_sim:
                best, best_sim = cue, sim
        if best is None or best_sim < 0.18:
            return {"found": False, "mode": "none", "text": None, "similarity": best_sim}
        if best_sim < 0.33:   # gist-level recognition only — the ghost signal
            return {"found": True, "mode": "ghost", "similarity": best_sim,
                    "text": f"(a sense of something about: {best.occasion})"}
        text = self.graph.reconstruct(best, self.models)   # full reconstruction
        return {"found": True, "mode": "reconstructed", "similarity": best_sim,
                "text": text, "cue": best.id}

    def journal(self, query: str) -> dict:
        """Deliberate escape hatch: freeze the best-matching reflection verbatim,
        turning a reconstruction into a fixed artifact (decision D10)."""
        probe = self.embed.embed(query)
        best, best_sim = None, 0.0
        for cue in self.graph.cues.values():
            sim = self.graph.recognise(cue, probe)
            if sim > best_sim:
                best, best_sim = cue, sim
        if best is None:
            return {"journaled": False}
        text = self.graph.reconstruct(best, self.models) if best.verbatim is None else best.verbatim
        best.verbatim = text
        self.trace(f"journaled reflection {best.id} verbatim")
        return {"journaled": True, "cue": best.id, "text": text}

    # --- continuity across restart (sleep, not death) ---
    def save(self, path) -> None:
        """Persist the durable self — the cold graph — so meno remains."""
        from . import persistence
        persistence.save(self.graph, path)

    def load(self, path) -> None:
        """Wake from a saved graph. The working set starts empty; recall works
        immediately, and resurface() can rebuild some working context."""
        from . import persistence
        persistence.load(self.graph, path)

    def resurface(self, k: int = 3) -> int:
        """Rebuild a little working context by re-entering the most salient
        memories as self-events — reconstruction at the scope of the whole self."""
        top = sorted(self.graph.nodes.values(), key=lambda n: n.salience, reverse=True)[:k]
        for node in top:
            ev = Event(content=node.content, kind=Kind.SELF, source="resurface",
                       activation=0.7, embedding=list(node.embedding))
            ev.payload["role"] = "resurface"
            self.bus.publish(ev)
        return self.run_until_quiescent()

    # --- observability ---
    def snapshot(self) -> dict:
        return {
            "events_seen": len(self.bus.log),
            "hot": self.working_set.depth(),
            "streams_active": len(self.streams.active),
            "streams_warm": len(self.streams.warm),
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "reflections": len(self.graph.cues),
        }
