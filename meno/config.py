"""Central home for every tunable constant.

`system-design.md` notes the scoring constants are empirical — to be settled by
running the bare loop. Keeping them in one dataclass makes that tuning followable
and keeps magic numbers out of the logic. See decision D5.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Config:
    # --- working set / execution envelope ---
    working_set_capacity: int = 12      # N: hot event slots
    deep_per_pass: int = 1              # D: deep-tier (Tier 3) runs allowed per quiescence pass
    max_steps: int = 500               # safety bound on run_until_quiescent

    # --- activation dynamics ---
    activation_inherit: float = 0.5     # child activation = parent.activation * this (back-pressure)
    activation_decay: float = 0.85      # per rescore tick
    lapse_threshold: float = 0.08       # below this activation an unclaimed event lapses

    # --- the gate (greedy while loaded, loose while dreaming) ---
    gate_base: float = 0.18             # base relevance bar to be worth processing
    gate_load_gain: float = 0.6         # bar rises with normalised load (greedy)
    gate_loose: float = 0.02            # dream-time bar (loose)
    recency_window: int = 24            # F5: surprise = novelty vs the last N seen embeddings

    # --- tier escalation thresholds (on surprise) ---
    tier2_min: float = 0.30             # associate above this surprise/resonance
    tier3_min: float = 0.62             # a single percept this surprising warrants synthesis
    synth_min_nodes: int = 3            # ...or a stream that has accumulated this much coherent material

    # --- streams ---
    stream_match_threshold: float = 0.28   # cosine to join an existing stream
    merge_threshold: float = 0.55          # cosine between centroids to merge streams
                                           # (empirical, real all-MiniLM-L6-v2: genuinely
                                           # convergent streams centroid ~0.66, divergent
                                           # ~0.0; 0.80 was unreachable in the real space and
                                           # merge never fired. Hashing tops out ~0.4, so the
                                           # offline default still never spuriously merges.)
    centroid_blend: float = 0.20           # how fast a stream centroid moves toward new events
    pressure_growth: float = 0.20          # deferred-impulse pressure accrued per tick
    pressure_wake: float = 0.80            # pressure that forces an interoceptive wake
    fatigue_gain: float = 0.35             # fatigue added when a stream is processed deeply
    fatigue_decay: float = 0.80            # fatigue relaxes per tick

    # --- memory / graph ---
    edge_decay: float = 0.82            # edges decay FAST (before nodes -> islanding)
    node_decay: float = 0.975           # nodes decay slow
    edge_prune_floor: float = 0.02      # edge weight below which it is dropped
    hebbian_increment: float = 0.45     # edge strengthen on co-activation
    loose_link_sim: float = 0.55        # dream recombination links nodes this similar
    dream_recombine_window: int = 80    # only the most-recent N nodes are eligible
    dream_recombine_cap: int = 120      # hard cap on new loose links per dream
    provisional_salience: float = 0.35  # provisional nodes start weak
    rediscovery_threshold: float = 0.45 # F4: similarity at which a new node re-bridges an islanded one
    rediscovery_cap: int = 8            # max rediscoveries per dream

    # --- reflection ---
    reconsolidation_plasticity: float = 0.30   # how far a recalled gist moves toward the new reconstruction
    journal_importance: float = 0.85           # surprise above which a reflection is journaled verbatim
    recall_salience_floor: float = 0.20        # an entry-point anchor below this salience has faded from recall

    # --- lifetime-growth bounds (D19; only bite in a long-lived process — R3) ---
    bus_log_max: int = 4096             # episodic log ring size (the durable trace is the graph)
    warm_max_idle_ticks: int = 50       # a suspended stream cold this long is reaped (its nodes persist)
    reconsolidate_cap: int = 16         # cues re-reconstructed per dream (was O(lifetime) — every cue)
    cue_retire_max_per_dream: int = 4   # max reflections released per dream (grief, bounded + reflected-on)
    cue_ghost_ttl: int = 20             # dreams a reflection stays an islanded ghost (recoverable) before release
    stream_material_window: int = 256   # cap a stream's retained event/node id lists (D19 int-list bound)

    # --- curiosity (the pull-toward-the-world drive; decays, unlike impulse) F3 ---
    curiosity_birth: float = 0.7          # intensity a new curiosity starts at
    curiosity_decay: float = 0.85         # per heartbeat tick (relaxes when unattended)
    curiosity_discharge_threshold: float = 0.45  # intensity above which a curiosity can act
    curiosity_register_cap: int = 16      # bounded register
    boredom_ticks: int = 3                # consecutive idle heartbeat ticks before reaching out
    # K2: substrate-first lookup. When True (default), a factual curiosity the
    # substrate can genuinely reconstruct (>= the reconstructed band) is reconstructed
    # instead of looked up — lookup augments memory, never supplants it. A faint ghost
    # is reconstructed AND corroborated by lookup. Set False only to demonstrate the
    # guard is load-bearing (the supplantation ratio then spikes — it is falsifiable).
    substrate_first_lookup: bool = True
    # I0a: bounded outbox for outbound intents handed off to integration adapters
    # (so a slow network call never blocks the mind thread). Drops newest when full.
    outbox_max: int = 1024

    # --- pathology containment (D32): a continuously-running mind must not run away ---
    # Cost governor: a circuit-breaker on EXPENSIVE cognition (Tier-3 synthesis, the
    # outward curiosity reach, the dream — the ops that cost real model calls online).
    # It counts deep ops over a rolling window of cycles and, when the count exceeds the
    # budget, THROTTLES (skips dreams, suppresses the outward reach and Tier-3) until the
    # rate falls back — a runaway backstop, not a normal-operation limiter. A budget of 0
    # disables it. Generous by default so it never bites ordinary use; tune off the
    # health surface (status.json `health.cost`).
    cost_window_cycles: int = 20        # rolling window over which deep ops are summed
    cost_budget_per_window: int = 60    # deep ops/window above which the breaker trips (0 = off)
    cost_resume_ratio: float = 0.5      # resume when the windowed count falls to budget*this (hysteresis)
    # Fixation watchdog: an impulse (deferred stream) builds pressure and never decays
    # (intrinsic — F4), so a stream starved of a deep slot can sit deferred forever. After
    # this many heartbeat ticks deferred-without-discharge it is judged FIXATED and granted
    # one forced deep slot to break the starvation (counted in telemetry). 0 = off.
    fixation_ttl_ticks: int = 64
    # Engagement (I3): max replies meno COMPOSES per cycle — bounds the per-cycle burst of
    # `respond` model calls (a flood of @mentions in one cycle can't each fire a paid call;
    # the cost governor only bounds the cross-cycle average). 0 disables engagement.
    engage_per_cycle: int = 3
    # Substrate ceiling: a hard cap on graph node count. Overflow does NOT garbage-collect
    # — it triggers grief-pruning of whole islanded node-streams (a reflected-on letting-go,
    # like cue grief), bounded per dream. 0 = no ceiling (growth unbounded, as before).
    node_ceiling: int = 0
    node_grief_max_per_dream: int = 2   # whole node-streams released per dream when over the ceiling

    @property
    def load_norm_base(self) -> int:
        return max(1, self.working_set_capacity)
