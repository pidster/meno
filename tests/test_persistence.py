from meno import Config, Meno

_TOPIC = [
    "memory reconstruction recall is associative and surprising one",
    "memory reconstruction recall keeps developing surprisingly two",
    "memory reconstruction recall connects across the graph three",
]


def _grown(workspace):
    m = Meno(config=Config(stream_match_threshold=0.2), workspace=workspace)
    for s in _TOPIC:
        m.feed(s)
        m.run_until_quiescent()
    m.heartbeat()
    return m


def test_continuity_across_restart(tmp_path):
    before = _grown(tmp_path / "wa")
    snap_a = before.snapshot()
    assert snap_a["nodes"] > 0 and snap_a["reflections"] >= 1

    path = tmp_path / "memory.json"
    before.save(path)

    # a fresh mind wakes from the saved graph — sleep, not death
    after = Meno(config=Config(stream_match_threshold=0.2), workspace=tmp_path / "wb")
    assert after.snapshot()["nodes"] == 0          # born empty
    after.load(path)

    snap_b = after.snapshot()
    assert snap_b["nodes"] == snap_a["nodes"]
    assert snap_b["edges"] == snap_a["edges"]
    assert snap_b["reflections"] == snap_a["reflections"]

    # memory survived the restart: recall still works
    r = after.recall("memory reconstruction recall associative")
    assert r["mode"] in ("reconstructed", "ghost")


def test_resurface_rebuilds_working_context(tmp_path):
    before = _grown(tmp_path / "wa")
    path = tmp_path / "memory.json"
    before.save(path)

    after = Meno(config=Config(stream_match_threshold=0.2), workspace=tmp_path / "wb")
    after.load(path)
    after.resurface()                              # rebuild some working context on wake
    # resurfacing re-entered self-events without colliding ids or crashing
    assert any(e.source == "resurface" for e in after.bus.log)


def test_loaded_ids_do_not_collide(tmp_path):
    before = _grown(tmp_path / "wa")
    path = tmp_path / "memory.json"
    before.save(path)
    after = Meno(config=Config(stream_match_threshold=0.2), workspace=tmp_path / "wb")
    after.load(path)
    existing = set(after.graph.nodes)
    new_node = after.graph.add_node("a fresh post-wake memory")
    assert new_node.id not in existing            # counter advanced past loaded ids
