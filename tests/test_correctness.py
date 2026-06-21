"""Tests pinning the P2 correctness fixes (decision D15) — each would have caught
the bug the adversarial review found."""
import tempfile

from meno import Config, HashingEmbedding, Meno
from meno.event import Event, Status
from meno.streams import StreamManager
from meno.working_set import WorkingSet


def mk(embed, text, **kw):
    e = Event(content=text, **kw)
    e.embedding = embed.embed(text)
    return e


def fresh(**cfg):
    return Meno(config=Config(**cfg), workspace=tempfile.mkdtemp(prefix="meno_corr_"))


# --- F9: demotion no longer destroys streams or evicts the whole None-cohort ---

def test_orphan_events_lapse_individually_not_as_a_cohort():
    embed = HashingEmbedding()
    cfg = Config(working_set_capacity=2)
    sm = StreamManager(embed, cfg)
    ws = WorkingSet(cfg, sm)
    # un-routed (stream_id None) events must not all be evicted at once
    for t in ["one", "two", "three", "four"]:
        ws.admit(mk(embed, t))   # no sm.route -> stream_id stays None
    assert ws.depth() == cfg.working_set_capacity   # not collapsed to 1
    assert not sm.warm                               # nothing suspended
    assert None not in ws.demoted_streams            # no garbage recorded


def test_oversized_single_stream_trims_to_capacity_not_to_one():
    embed = HashingEmbedding()
    cfg = Config(working_set_capacity=3, stream_match_threshold=0.3)
    sm = StreamManager(embed, cfg)
    ws = WorkingSet(cfg, sm)
    last = None
    for t in ["one topic", "two topic", "three topic", "four topic", "five topic"]:
        last = mk(embed, t)
        sm.route(last)
        ws.admit(last)
    assert ws.depth() == cfg.working_set_capacity    # trimmed to N, not collapsed to ~1
    assert last.stream_id in sm.active               # the stream survived (not destroyed)
    assert not sm.warm                               # a too-big stream is trimmed, not suspended


# --- F10: per-instance id counters; load must not clobber another instance ---

def test_ids_are_per_instance_and_load_does_not_collide(tmp_path):
    m1 = fresh()
    a = m1.graph.add_node("alpha")
    b = m1.graph.add_node("beta")            # ids 1, 2 in m1

    m2 = fresh()
    m2.graph.add_node("x")
    path = tmp_path / "m2.json"
    m2.save(path)

    m3 = fresh()
    m3.load(path)                            # would have reset a global counter in the old code

    c = m1.graph.add_node("gamma")
    assert c.id == 3 and c.id not in (a.id, b.id)
    assert set(m1.graph.nodes) == {1, 2, 3}  # nothing in m1 was overwritten
    # m3 continues past the loaded maximum
    d = m3.graph.add_node("delta")
    assert d.id > max(int(n) for n in m3.graph.nodes if n != d.id)


# --- M2: route picks the genuinely best stream before the threshold test ---

def test_route_selects_highest_cosine_stream():
    embed = HashingEmbedding()
    sm = StreamManager(embed, Config(stream_match_threshold=0.99))
    a = mk(embed, "alpha alpha alpha")
    b = mk(embed, "beta beta beta")
    sm.route(a); sm.route(b)                 # forced apart by the high threshold
    assert a.stream_id != b.stream_id
    sm.cfg = Config(stream_match_threshold=0.2)   # now allow joining
    probe = mk(embed, "alpha alpha beta")         # closer to a than to b
    sm.route(probe)
    assert probe.stream_id == a.stream_id         # joined the best match, not b, not a new stream


# --- L4: journaling freezes without first drifting the cue ---

def test_journal_does_not_reconsolidate_the_cue():
    m = fresh(stream_match_threshold=0.2)
    for s in ["memory reconstruction recall one",
              "memory reconstruction recall two",
              "memory reconstruction recall three"]:
        m.feed(s)
        m.run_until_quiescent()
    m.heartbeat()
    assert m.snapshot()["reflections"] >= 1
    recalls_before = {cid: c.recalls for cid, c in m.graph.cues.items()}

    j = m.journal("memory reconstruction recall")
    assert j["journaled"] is True
    cue = m.graph.cues[j["cue"]]
    assert cue.verbatim is not None                       # frozen
    assert cue.recalls == recalls_before[cue.id]          # freezing did NOT drift it
    # and it now reconstructs stably to the frozen text
    assert m.graph.reconstruct(cue, m.models) == cue.verbatim
