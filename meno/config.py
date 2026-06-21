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

    # --- tier escalation thresholds (on surprise) ---
    tier2_min: float = 0.30             # associate above this surprise/resonance
    tier3_min: float = 0.62             # synthesise above this surprise

    # --- streams ---
    stream_match_threshold: float = 0.28   # cosine to join an existing stream
    merge_threshold: float = 0.80          # cosine between centroids to merge streams
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

    # --- reflection ---
    reconsolidation_plasticity: float = 0.30   # how far a recalled gist moves toward the new reconstruction
    journal_importance: float = 0.85           # surprise above which a reflection is journaled verbatim

    @property
    def load_norm_base(self) -> int:
        return max(1, self.working_set_capacity)
