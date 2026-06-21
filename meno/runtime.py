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
from .curiosity import CuriosityRegister
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
        self.bus = Bus(log_max=self.cfg.bus_log_max)
        self.curiosities = CuriosityRegister(self.cfg)   # F3: the pull-toward-the-world drive
        self.consolidation = ConsolidationCycle(self)
        self.controller = Controller(self)
        self.processors = processors or DEFAULT_PROCESSORS
        self.workspace = Path(workspace or ".meno_workspace")
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.verbose = verbose
        self.deep_budget = self.cfg.deep_per_pass
        self._idle_ticks = 0          # boredom: persists across heartbeats (R2 autonomy)
        self._curiosity_cursor = 0    # rotates top-down curiosity target + framing
        self._last_curiosity_ref = None   # anti-repeat: don't wonder twice in a row about one node
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
        """The quiet phase. Two kinds of initiative compete for the spare slot, and
        **impulses come first** (finish unfinished cognition before wandering):
        interoceptive wakes resurface deferred streams; only when no impulse fired
        and meno has been *under-stimulated* for `boredom_ticks` does **curiosity**
        reach toward the world (model-routed discharge — F3).

        Boredom (`_idle_ticks`) PERSISTS across calls and resets on genuine activity,
        so a sustained-quiet mind under continuous operation eventually reaches out
        on its own — even with no fresh stimulus to keep the quiet phase awake. Per
        call the loop still breaks early when nothing is happening; the persistent
        counter is what lets boredom accumulate over the driver's many short
        heartbeats (R2)."""
        total = 0
        for _ in range(ticks):
            wakes = self.controller.tick()                  # impulses first
            for w in wakes:
                self.bus.publish(w)
            if wakes:
                self._idle_ticks = 0                         # impulses take the slot
            elif self.working_set.depth() == 0 and not self.bus.pending():
                self._idle_ticks += 1
                deferred_pending = (any(s.deferred for s in self.streams.active.values())
                                    or any(s.deferred for s in self.streams.warm.values()))
                # impulses-first, properly: don't wander while unfinished cognition
                # is still pending — even if its pressure hasn't yet crossed the
                # wake line (timing must not let curiosity jump the queue).
                if self._idle_ticks >= self.cfg.boredom_ticks and not deferred_pending:
                    if self.curiosities.top() is None:
                        self._birth_topdown_curiosity()
                    for ev in self._discharge_curiosity():
                        self.bus.publish(ev)
                    self._idle_ticks = 0                     # acted -> re-accumulate boredom
            else:
                self._idle_ticks = 0                         # busy mind is not bored
            total += self.run_until_quiescent()
            self.curiosities.decay()                         # curiosities relax over time
            deferred_left = (any(s.deferred for s in self.streams.active.values())
                             or any(s.deferred for s in self.streams.warm.values()))
            top = self.curiosities.top()
            curious = top is not None and top.intensity >= self.cfg.curiosity_discharge_threshold
            if not wakes and not deferred_left and not curious:
                break
        return total

    # --- curiosity (F3): birth and model-routed discharge ---
    _WONDER_FRAMES = (
        "what more is there about {x}?",
        "what connects {x} to the rest?",
        "what have I been missing about {x}?",
        "why does {x} matter the way it does?",
    )

    def _birth_topdown_curiosity(self) -> None:
        """Boredom reaches for a NEGLECTED memory, not the most-attended one (doc 05,
        Approaches 1+3). Genuine curiosity pulls toward the under-explored middle —
        nodes with few surviving associations — and rotates target and framing with
        an anti-repeat guard, so sustained boredom doesn't become a metronome firing
        the same wonder about the same hub (R2 review). Reaching for argmax(salience)
        would also entrench that hub (repeated co-activation raises its salience),
        collapsing the graph onto one attractor — the opposite of idiosyncrasy."""
        if not self.graph.nodes:
            return
        degree: dict = {}
        for (a, b) in self.graph.edges:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        floor = self.cfg.recall_salience_floor
        present = [n for n in self.graph.nodes.values() if n.content != self._last_curiosity_ref]
        cands = [n for n in present if n.salience >= floor] or present \
            or list(self.graph.nodes.values())
        # the neglected MIDDLE, in full: everything at or below the median degree —
        # so a large under-explored region isn't starved behind a fixed window, while
        # the well-connected hubs (above median) stay off the wondering path. The
        # cursor then walks this whole set over time, fewest-associations first.
        degs = sorted(degree.get(n.id, 0) for n in cands)
        median = degs[len(degs) // 2] if degs else 0
        neglected = [n for n in cands if degree.get(n.id, 0) <= median]
        neglected.sort(key=lambda n: (degree.get(n.id, 0), n.created_at))
        node = neglected[self._curiosity_cursor % len(neglected)]
        frame = self._WONDER_FRAMES[self._curiosity_cursor % len(self._WONDER_FRAMES)]
        self._curiosity_cursor += 1
        self._last_curiosity_ref = node.content
        self.curiosities.register(frame.format(x=node.content[:40]),
                                  source="top-down", referent=node.content)

    def _discharge_curiosity(self) -> List[Event]:
        """Let the model route the top curiosity across the internal/external
        matrix: an inward thought, an outward action (the Effector self-fires),
        both, or neither-yet."""
        cur = self.curiosities.top()
        if cur is None or cur.intensity < self.cfg.curiosity_discharge_threshold:
            return []
        route = self.models.wonder(cur.text, cur.referent)
        emitted: List[Event] = []
        mode = route.get("mode", "internal")
        if mode in ("internal", "both") and route.get("thought"):
            ev = Event(content=route["thought"], kind=Kind.SELF, source="curiosity")
            ev.payload["role"] = "wonder"
            emitted.append(ev)
        if mode in ("external", "both") and route.get("action"):
            act = dict(route["action"])
            ev = Event(content=f"intent: {act.get('action')} {act.get('path', '')}",
                       kind=Kind.INTENT, source="curiosity", payload=act)
            emitted.append(ev)
        cur.intensity *= 0.3                                  # discharged — relaxes
        self.trace(f"curiosity discharged ({mode}): {cur.text[:40]!r}")
        return emitted

    # --- circadian: the dream ---
    def dream(self) -> dict:
        report = self.consolidation.run()
        self.deep_budget = self.cfg.deep_per_pass   # rested: deep capacity replenished
        return report

    # --- tiered recall (reconstructive reflection) ---
    def recall(self, query: str) -> dict:
        probe = self.embed.embed_cold(query)   # COLD: probe must share the cue-gist space (D20)
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
        probe = self.embed.embed_cold(query)   # COLD: probe must share the cue-gist space (D20)
        best, best_sim = None, 0.0
        for cue in self.graph.cues.values():
            sim = self.graph.recognise(cue, probe)
            if sim > best_sim:
                best, best_sim = cue, sim
        if best is None:
            return {"journaled": False}
        # freeze WITHOUT reconsolidating — journaling shouldn't drift the cue first (D15)
        text = (best.verbatim if best.verbatim is not None
                else self.graph.reconstruct(best, self.models, reconsolidate=False))
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
            # re-enter the *content* as a fresh stimulus; let the annotator embed it
            # HOT for routing — injecting the node's cold vector would cross spaces (D20).
            ev = Event(content=node.content, kind=Kind.SELF, source="resurface",
                       activation=0.7)
            ev.payload["role"] = "resurface"
            self.bus.publish(ev)
        return self.run_until_quiescent()

    # --- observability ---
    def snapshot(self) -> dict:
        return {
            "events_seen": self.bus.total_published,    # lifetime (log itself is bounded)
            "hot": self.working_set.depth(),
            "streams_active": len(self.streams.active),
            "streams_warm": len(self.streams.warm),
            "nodes": len(self.graph.nodes),
            "edges": len(self.graph.edges),
            "reflections": len(self.graph.cues),
            "curiosities": len(self.curiosities.items),
        }
