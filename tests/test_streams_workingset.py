from meno import Config, HashingEmbedding
from meno.event import Event
from meno.streams import StreamManager
from meno.working_set import WorkingSet


def mk(embed, text, **kw):
    e = Event(content=text, **kw)
    e.embedding = embed.embed(text)
    return e


def test_route_spawns_and_joins():
    embed = HashingEmbedding()
    sm = StreamManager(embed, Config(stream_match_threshold=0.2))
    a = mk(embed, "database connection pool exhausted")
    b = mk(embed, "database connection dropped under load")
    c = mk(embed, "banana smoothie recipe ideas")
    sm.route(a); sm.route(b); sm.route(c)
    assert a.stream_id == b.stream_id          # similar -> same stream
    assert c.stream_id != a.stream_id          # unrelated -> its own stream


def test_merge_converges():
    embed = HashingEmbedding()
    # high join bar keeps them apart at routing; lower merge bar lets them converge
    sm = StreamManager(embed, Config(stream_match_threshold=0.99, merge_threshold=0.3))
    a = mk(embed, "alpha beta gamma topic")
    b = mk(embed, "alpha beta delta topic")        # similar but not identical
    sm.route(a); sm.route(b)
    assert a.stream_id != b.stream_id              # two separate trains of thought
    merges = sm.detect_merge()
    assert merges
    sm.merge(*merges[0])
    assert len(sm.active) == 1                      # converged into one


def test_suspend_resume_roundtrip():
    embed = HashingEmbedding()
    sm = StreamManager(embed, Config())
    e = mk(embed, "a line of thought")
    sm.route(e)
    sid = e.stream_id
    sm.suspend(sid)
    assert sid in sm.warm and sid not in sm.active
    sm.resume(sid)
    assert sid in sm.active and sid not in sm.warm


def test_deferred_pressure_builds_and_wakes():
    embed = HashingEmbedding()
    cfg = Config(pressure_growth=0.5, pressure_wake=0.8)
    sm = StreamManager(embed, cfg)
    e = mk(embed, "unfinished thought")
    sm.route(e)
    sm.active[e.stream_id].deferred = True
    fired = any(e.stream_id in sm.tick() for _ in range(5))
    assert fired                                # interoceptive wake eventually fires


def test_working_set_capacity_demotes_whole_stream():
    embed = HashingEmbedding()
    cfg = Config(working_set_capacity=3, stream_match_threshold=0.9)
    sm = StreamManager(embed, cfg)
    ws = WorkingSet(cfg, sm)
    for t in ["alpha one", "beta two", "gamma three", "delta four", "epsilon five"]:
        e = mk(embed, t)
        sm.route(e)
        ws.admit(e)
    assert ws.depth() <= cfg.working_set_capacity
    assert sm.warm                              # overflow demoted a whole stream


def test_rescore_lapses_quiet_events():
    cfg = Config(activation_decay=0.1, lapse_threshold=0.5)
    sm = StreamManager(HashingEmbedding(), cfg)
    ws = WorkingSet(cfg, sm)
    e = mk(HashingEmbedding(), "fading", activation=0.6)
    sm.route(e)
    ws.admit(e)
    ws.rescore()                                # 0.6*0.1 = 0.06 < 0.5
    assert ws.depth() == 0
