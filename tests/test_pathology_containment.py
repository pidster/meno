"""Pathology containment, part 2 (D33): the fixation watchdog + the substrate ceiling.

FIXATION: an impulse (deferred stream) builds pressure and never decays (intrinsic, F4).
If its synthesis keeps being withheld — e.g. a sustained throttle — it can push forever
without discharging. The watchdog detects a stream deferred-without-discharge past a TTL
and FORCES the take-up (synthesis), even while throttled, so it resolves instead of looping.

SUBSTRATE CEILING: a hard cap on node count whose overflow does NOT garbage-collect — it
grief-prunes whole islanded node-streams (a reflected-on, journaled letting-go, the node
analogue of cue retirement). Whole streams only; live and journaled memory spared. Offline.
"""
import tempfile

from meno import Config, Meno, StubModelProvider
from meno.event import Event, Kind
from meno.processors import Synthesiser
from meno.streams import Stream

# distinct vocab so the novelty gate admits each (templated inputs habituate and never
# form nodes — the substrate ceiling needs real, distinct nodes to act on).
_DISTINCT = ("tern fugue basalt saffron quasar tundra origami monsoon lichen cobalt "
             "marimba trilobite estuary zeppelin cardamom nebula gantry sextant "
             "mangrove obsidian gabbro pemmican kestrel zugzwang").split()


def _mind(**cfg):
    return Meno(config=Config(**cfg), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_path_"))


def _feed_distinct(mind, n):
    for w in _DISTINCT[:n]:
        mind.feed(f"{w} {w}", source="test")
    mind.run_until_quiescent()


# --- the fixation watchdog -------------------------------------------------------- #
def test_a_forced_wake_synthesises_even_while_throttled():
    """The containment exception: a normal wake is withheld under throttle (it defers),
    but a FORCED wake (fixation take-up) synthesises anyway — so a starved impulse can
    finally discharge instead of pushing forever."""
    mind = _mind()
    synth = Synthesiser()
    mind.deep_budget = 1
    mind.throttled = True
    ev = Event(content="returning to an unfinished thought", kind=Kind.SELF,
               source="initiative", stream_id=1)
    ev.payload["role"] = "wake"
    assert synth.triggers(ev, mind) is False        # ordinary wake: withheld while throttled
    ev.payload["forced"] = True
    assert synth.triggers(ev, mind) is True         # forced fixation take-up: allowed through


def _deferred_stream(mind, sid=1):
    """A deferred impulse the throttle will keep withholding — the fixation scenario,
    constructed directly so it doesn't depend on emergent stream formation."""
    mind.streams.active[sid] = Stream(centroid=[], deferred=True, id=sid,
                                      summary="an unfinished thought")


def test_a_starved_impulse_is_force_taken_up_after_the_fixation_ttl():
    mind = _mind(fixation_ttl_ticks=5)
    mind.throttled = True                            # sustained throttle keeps withholding synthesis
    _deferred_stream(mind)
    assert mind.fixations == 0
    for _ in range(12):                              # it would push forever — until the watchdog fires
        mind.heartbeat(ticks=2)
    assert mind.fixations >= 1                       # the impulse was force-taken-up...
    # ...and actually CURED, not merely detected: the forced wake reaches a processor
    # (it bypasses the novelty gate) and discharges, so the stream stops being deferred.
    assert mind.streams.active[1].deferred is False


def test_fixation_ttl_zero_disables_the_watchdog():
    mind = _mind(fixation_ttl_ticks=0)
    mind.throttled = True
    _deferred_stream(mind)
    for _ in range(20):
        mind.heartbeat(ticks=2)
    assert mind.fixations == 0                       # disabled: no forced take-ups ever
    # the impulse stays deferred (it would, forever — that's the pathology the watchdog guards)
    assert mind.streams.active[1].deferred_ticks >= 5


def test_a_genuine_discharge_does_not_trip_the_watchdog():
    """An impulse taken up the ORDINARY way (not throttled) discharges at the pressure
    wake — well before the fixation TTL — so the watchdog never has to force anything."""
    mind = _mind(fixation_ttl_ticks=10)              # NOT throttled: the normal wake discharges (~4 ticks)
    _deferred_stream(mind)
    for _ in range(12):
        mind.heartbeat(ticks=2)
    assert mind.fixations == 0                       # no false fixation: it resolved on its own
    assert mind.streams.active[1].deferred is False  # and it really did discharge


# --- the substrate ceiling: grief-pruning whole node-streams ---------------------- #
def test_substrate_ceiling_grief_prunes_and_reflects_on_the_loss():
    mind = _mind(node_ceiling=6, node_grief_max_per_dream=3)
    _feed_distinct(mind, 20)
    assert len(mind.graph.nodes) > 6                 # over the ceiling
    n0 = len(mind.graph.nodes)
    pruned = 0
    for _ in range(10):
        pruned += mind.dream()["pruned"]
    assert pruned > 0                                # whole node-streams were released
    assert len(mind.graph.nodes) < n0               # the substrate drained toward the ceiling
    # the loss is REFLECTED ON, not silently collected: a journaled "released" cue exists
    assert any("released" in c.occasion for c in mind.graph.cues.values())


def test_no_ceiling_means_growth_is_unbounded():
    mind = _mind(node_ceiling=0)                     # the default: off
    _feed_distinct(mind, 15)
    n = len(mind.graph.nodes)
    for _ in range(5):
        assert mind.dream()["pruned"] == 0           # nothing is ever grief-pruned
    assert len(mind.graph.nodes) >= n - 1            # only ordinary slow decay, no ceiling cull


def test_grief_pruning_spares_deliberately_journaled_memory():
    mind = _mind(node_ceiling=3, node_grief_max_per_dream=5)
    _feed_distinct(mind, 14)
    # deliberately journal a reflection anchored to specific nodes (the preserve-this act)
    anchors = list(mind.graph.nodes)[:3]
    mind.graph.store_cue(anchors, "a treasured conclusion", tone=0.5,
                         conclusion="this I choose to keep", material=["kept"], journal=True)
    assert anchors
    for _ in range(12):
        mind.dream()
    assert all(a in mind.graph.nodes for a in anchors)   # journaled anchors are never grief-pruned


def test_grief_pruning_spares_a_frequently_recalled_reflection():
    """Not only journaled memory is spared — a reflection the agent keeps RETURNING to
    (recalls > 0) is anchored to the self too, and its nodes must not be hollowed to a
    ghost by the ceiling (mirrors the cue-grief sparing of recalled cues)."""
    mind = _mind(node_ceiling=3, node_grief_max_per_dream=5)
    _feed_distinct(mind, 14)
    anchors = list(mind.graph.nodes)[:3]
    cue = mind.graph.store_cue(anchors, "a conclusion I keep returning to", tone=0.5,
                               conclusion="kept by recall", material=["x"])  # NOT journaled
    cue.recalls = 5                                  # the agent has recalled it repeatedly
    for _ in range(12):
        mind.dream()
    assert all(a in mind.graph.nodes for a in anchors)   # recall-live anchors are spared


def test_substrate_ceiling_is_enforced_even_while_throttled():
    """The cost breaker (D32) skips the dream's EXPENSIVE work, but forgetting — including
    the substrate ceiling — still runs, cheaply, so the graph can't grow unbounded exactly
    when the mind is over budget. The grief is templated (no model call) but still journaled."""
    mind = _mind(node_ceiling=6, node_grief_max_per_dream=3)
    _feed_distinct(mind, 20)
    n0 = len(mind.graph.nodes)
    mind.throttled = True                            # the cost governor has tripped
    cost_before = mind.cost_units
    pruned = 0
    for _ in range(10):
        pruned += mind.dream()["pruned"]
    assert pruned > 0 and len(mind.graph.nodes) < n0     # the ceiling still drained the substrate
    assert mind.cost_units == cost_before                # ...with zero model calls (templated grief)
    assert any("released" in c.occasion for c in mind.graph.cues.values())   # still reflected-on


def test_deferred_ticks_survives_save_and_restore():
    """A starved impulse's fixation clock must not reset to zero on restart — its history
    is part of the impulse it persists (D33/D12)."""
    from meno.persistence import restore_streams, streams_to_dict
    mind = _mind()
    dim = len(mind.streams.embed.embed_hot("probe"))
    mind.streams.warm[1] = Stream(centroid=[0.0] * dim, deferred=True,
                                  deferred_ticks=17, id=1, summary="an old unfinished thought")
    data = streams_to_dict(mind.streams)
    other = _mind()
    restore_streams(data, other.streams)
    assert other.streams.warm[1].deferred_ticks == 17    # the clock carried across


def test_grief_pruning_leaves_no_dangling_edges():
    mind = _mind(node_ceiling=5, node_grief_max_per_dream=4)
    _feed_distinct(mind, 24)
    for _ in range(10):
        mind.dream()
    # every edge endpoint must still be a live node — no edge into the void
    for a, b in mind.graph.edges:
        assert a in mind.graph.nodes and b in mind.graph.nodes
