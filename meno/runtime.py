"""The runtime: wires every component into one mind and drives the loop.

The deterministic core is synchronous and step-driven (`run_until_quiescent`) so
behaviour is reproducible and the scoring constants are tunable (decision D7). A
live async/threaded driver for real sensors is a thin wrapper to add later; the
kernel only requires *bounded* concurrency, which the worker-budget models.
"""
from __future__ import annotations

import queue
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
from .library import Library, Reference, seed_library
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
                 name: str = "meno",
                 verbose: bool = False) -> None:
        self.cfg = config or Config()
        self.name = name              # its ADDRESSABLE name (the handle) — what it answers to (I3)
        self.embed = embed or HashingEmbedding()
        self.models = models or StubModelProvider()
        self.graph = Graph(self.embed, self.cfg)
        # Reference memory — the anti-substrate (K1). Disjoint from the graph: never
        # an entry point for spreading activation, never in graph.cues. Seeded with a
        # lookup-able copy of the self-model + a tiny dictionary/thesaurus.
        self.library = seed_library()
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
        # pathology containment (D32): `throttled` is set by the driver's cost governor
        # — while True the mind suppresses its EXPENSIVE cognition (Tier-3 synthesis and
        # the outward curiosity reach). `cost_units` is the monotonic deep-op counter the
        # governor samples per cycle. Default off / zero, so a bare Meno is unchanged.
        self.throttled = False
        self.cost_units = 0
        self.fixations = 0            # D33: impulses force-taken-up after the fixation TTL
        self.engage_budget = self.cfg.engage_per_cycle   # I3: replies composable this cycle
                                                         # (the driver resets it each cycle)
        # K2 supplantation telemetry: lookups fired; of the factual curiosities the
        # substrate COULD serve (reconstructable), how many we still looked up
        # (supplanted) vs preferred memory. The don't-become-a-lookup-machine guard.
        self.lookup_tel = {"lookups": 0, "reconstructable_opportunities": 0, "supplanted": 0}
        # I0a: outbound intents the kernel hands OFF the mind thread to integration
        # adapters (a Driver worker drains this); the mind enqueues and moves on, so a
        # slow outward action never blocks cognition. Bounded; empty unless adapters run.
        self.outbox: "queue.Queue[dict]" = queue.Queue(maxsize=self.cfg.outbox_max)
        self.outbox_drops = 0                  # outbound intents dropped at a full outbox
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
    def feed(self, text: str, source: str = "chat", kind: Kind = Kind.SENSE, **payload) -> Event:
        ev = Event(content=text, kind=kind, source=source, payload=payload)
        self.bus.publish(ev)
        return ev

    def submit(self, event: Event) -> Event:
        self.bus.publish(event)
        return event

    # --- the gate at ingress: discard (habituate) or admit ---
    # A few kinds bypass the novelty gate: an INTENT is a *committed decision to act*
    # and a REFERENCE is a *looked-up fact that must inform/curate* — neither is a
    # percept to triage, and habituating one (e.g. a knowledge lookup whose text echoes
    # the curiosity that spawned it) would silently drop the action. Senses/derived
    # thoughts are still gated (that is where habituation belongs).
    _UNGATED = (Kind.INTENT, Kind.REFERENCE)

    def _ingest(self) -> None:
        for ev in self.bus.drain():
            self.annotator.annotate(ev)
            # a FORCED wake (D33 fixation take-up) must reach a processor — the whole point
            # is to guarantee the starved impulse is finally synthesised. A resurfaced wake
            # is otherwise an ordinary SELF event and could be habituated away at this gate,
            # leaving the watchdog detecting fixation but never curing it.
            if ev.kind in self._UNGATED or ev.payload.get("forced") or self.annotator.passes(ev):
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
        # relevance-but-unaffordable -> defer (build pressure), do not discard. Budget
        # exhaustion OR a tripped cost governor (D32) both defer the want, so throttled
        # deep work resurfaces later rather than lapsing silently.
        if self._synth and self._synth.wants(ev, self) and (self.deep_budget <= 0 or self.throttled):
            st = self.streams.get(ev.stream_id)
            if st is not None and not st.deferred:
                st.deferred = True
                self.trace(f"deferred (deep work withheld) -> stream {ev.stream_id}")
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
                # the outward reach is EXPENSIVE (model-routed wonder); a tripped cost
                # governor suppresses it while throttled (D32) — impulses still resurface
                # (cheap, internal), the agent just stops reaching toward the world.
                if (self._idle_ticks >= self.cfg.boredom_ticks and not deferred_pending
                        and not self.throttled):
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

    @property
    def supplantation_ratio(self) -> float:
        """Of the factual curiosities the substrate could GENUINELY serve (a real
        reconstruction was available), the fraction we looked up anyway instead of
        reconstructing. The don't-become-a-lookup-machine guard (K2): lookup must
        augment memory, never supplant it. ~0 with substrate-first on; a falsifiable
        metric — turn `cfg.substrate_first_lookup` off and it spikes to ~1, proving the
        guard is load-bearing and not a tautology. (A faint ghost corroborated by
        lookup is NOT supplantation: memory was reconstructed too.) These are lifetime
        counters — the guard is a standing one, not windowed."""
        opp = self.lookup_tel["reconstructable_opportunities"]
        return self.lookup_tel["supplanted"] / opp if opp else 0.0

    def _discharge_curiosity(self) -> List[Event]:
        """Let the model route the top curiosity across the internal/external matrix:
        an inward thought, an outward action (the Effector self-fires), both, or
        neither-yet. SUBSTRATE-FIRST (K2): consult memory before looking a fact up.
        A curiosity the substrate can genuinely reconstruct (the reconstructed band) is
        reconstructed, not looked up; a faint ghost is reconstructed AND corroborated
        by a lookup; only when memory is insufficient does the lookup stand alone —
        lookup augments the self, it never supplants it."""
        cur = self.curiosities.top()
        if cur is None or cur.intensity < self.cfg.curiosity_discharge_threshold:
            return []
        route = self.models.wonder(cur.text, cur.referent)
        self.cost_units += 1                                 # the outward reach: a deep op (D32)
        mode = route.get("mode", "internal")
        action = route.get("action")
        wanted_lookup = bool(action) and action.get("action") in ("lookup", "define")

        # substrate-first: a factual lookup consults memory first. recall() returns the
        # band: 'reconstructed' (>=0.33, memory serves it) / 'ghost' (faint trace) /
        # 'none'. We compute the band regardless of the policy flag so the metric stays
        # falsifiable; we only ACT on it (suppress / corroborate) when the flag is on.
        strong = False
        if wanted_lookup:
            recon = self.recall(cur.text)                    # actually reconstructs (>=0.33)
            strong = recon["mode"] == "reconstructed"
            ghost = recon["mode"] == "ghost"
            if strong:
                self.lookup_tel["reconstructable_opportunities"] += 1
            if self.cfg.substrate_first_lookup:
                if strong:                                   # memory serves it: reconstruct, don't look up
                    mode, action = "internal", None
                    route["thought"] = recon["text"]
                elif ghost:                                  # faint trace: reconstruct AND corroborate
                    mode = "both"
                    route["thought"] = recon["text"]

        emitted: List[Event] = []
        if mode in ("internal", "both") and route.get("thought"):
            ev = Event(content=route["thought"], kind=Kind.SELF, source="curiosity")
            ev.payload["role"] = "wonder"
            emitted.append(ev)
        if mode in ("external", "both") and action:
            act = dict(action)
            if act.get("action") in ("lookup", "define"):
                self.lookup_tel["lookups"] += 1
                if strong:    # looked up despite a genuine reconstruction -> supplantation
                    self.lookup_tel["supplanted"] += 1
            target = act.get("path") or act.get("key") or act.get("term") or ""
            ev = Event(content=f"intent: {act.get('action')} {target}",
                       kind=Kind.INTENT, source="curiosity", payload=act)
            emitted.append(ev)
        cur.intensity *= 0.3                                  # discharged — relaxes
        self.trace(f"curiosity discharged ({mode}): {cur.text[:40]!r}")
        return emitted

    # --- circadian: the dream ---
    def dream(self) -> dict:
        report = self.consolidation.run()
        # the dream's model-call-bearing ops (merges = relate, retires = grief synthesis)
        # count toward the governor's deep-op tally (D32). While throttled the dream runs
        # CHEAPLY (those passes skip / template), so it costs ~nothing — letting the
        # governor's window drain and the breaker reset.
        if not self.throttled:
            self.cost_units += 1 + report.get("merges", 0) + report.get("retired", 0)
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
    @property
    def library_path(self) -> Path:
        """The Library's own home, beside the substrate (instance-layout): the
        reference shelf persists separately from the identity-bearing graph."""
        return self.workspace / "library" / "index.json"

    def save(self, path) -> None:
        """Persist the durable self — the cold graph AND the warm tier (suspended
        streams), so meno remains and a restart can resume mid-thought (R4). The
        Library (reference, not identity) is saved to its own home under the
        workspace, kept out of the substrate file (K1; episodic≠semantic on disk)."""
        from . import persistence
        persistence.save(self.graph, path, streams=self.streams)
        self.library.save(self.library_path)

    def load(self, path) -> None:
        """Wake from a saved graph + warm tier. The working set starts empty; recall
        works immediately, suspended streams are restored (their deferred pressure
        resumes them via the heartbeat), and resurface() rebuilds working context.
        The Library is restored from its own home if present (else the seed stands)."""
        from . import persistence
        persistence.load(self.graph, path, streams=self.streams)
        if self.library_path.exists():
            self.library = Library.load(self.library_path)
            # The self-model is the TYPE (D24), baked in the image — never trust a
            # persisted copy that may predate an image upgrade. Always re-derive it
            # from the canonical constant so a looked-up "self-model" can't go stale.
            from .self_model import MENO_SELF
            self.library.put(Reference(key="self-model", body=MENO_SELF,
                                       source="meno:type", kind="reference"))

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
            "fixations": self.fixations,            # impulses force-taken-up past the TTL (D33)
        }
