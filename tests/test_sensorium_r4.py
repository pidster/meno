"""R4 — a real afferent channel + warm-tier persistence.

Sensorium tests assert the consent/privacy/resource BOUNDS (not just that it
reads), because an autonomous agent wired to the filesystem is exactly where
those boundaries matter. Persistence tests assert a restart resumes MID-THOUGHT
(the warm tier), and — the theory check — that resumption reconstructs through
the *evolved* graph, picking up a connection formed while suspended.
"""
import os
import tempfile
from pathlib import Path

from meno import (
    Config,
    Driver,
    FilesystemSensor,
    Meno,
    StubModelProvider,
)
from meno.embeddings import HashingEmbedding


def mind() -> Meno:
    return Meno(config=Config(), embed=HashingEmbedding(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_r4_"))


def _tmproot() -> Path:
    return Path(tempfile.mkdtemp(prefix="meno_fs_"))


# --- sensorium: it senses the world, within bounds ------------------------- #
def test_filesystem_sensor_emits_a_percept_for_a_new_file():
    root = _tmproot()
    (root / "note.md").write_text("a thought about volcanoes and memory")
    s = FilesystemSensor(root)
    percepts = s.poll()
    assert len(percepts) == 1
    text, source, payload = percepts[0]
    assert source == "filesystem" and "volcanoes" in text
    assert payload["path"].endswith("note.md")


def test_filesystem_sensor_only_reports_changes():
    root = _tmproot()
    f = root / "a.txt"
    f.write_text("first")
    s = FilesystemSensor(root)
    assert len(s.poll()) == 1          # new file
    assert s.poll() == []              # unchanged -> nothing
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime + 10))   # touch -> changed
    assert len(s.poll()) == 1


def test_filesystem_sensor_skips_hidden_and_non_text_and_oversized():
    root = _tmproot()
    (root / "visible.md").write_text("ok")
    (root / ".secret.env").write_text("API_KEY=should-never-be-read")    # hidden
    (root / "image.png").write_text("binary-ish")                       # wrong suffix
    (root / "huge.txt").write_text("x" * 200)                           # over max_bytes
    dotdir = root / ".git"
    dotdir.mkdir()
    (dotdir / "config.txt").write_text("under a dotdir")                 # hidden dir
    s = FilesystemSensor(root, max_bytes=50)
    texts = " ".join(t for t, _, _ in s.poll())
    assert "ok" in texts
    assert "API_KEY" not in texts and "should-never-be-read" not in texts
    assert "binary-ish" not in texts
    assert "under a dotdir" not in texts
    assert "xxxx" not in texts          # oversized skipped


def test_filesystem_sensor_does_not_escape_root_via_symlink():
    root = _tmproot()
    outside = _tmproot()
    (outside / "secret.txt").write_text("outside the consented root")
    try:
        os.symlink(outside / "secret.txt", root / "link.txt")
    except (OSError, NotImplementedError):
        return                          # platform without symlinks: skip
    s = FilesystemSensor(root)
    texts = " ".join(t for t, _, _ in s.poll())
    assert "outside the consented root" not in texts


def test_filesystem_sensor_caps_files_per_poll():
    root = _tmproot()
    for i in range(20):
        (root / f"f{i}.txt").write_text(f"file {i}")
    s = FilesystemSensor(root, max_per_poll=5)
    assert len(s.poll()) == 5


def test_driver_senses_the_world_through_a_filesystem_channel():
    root = _tmproot()
    (root / "seed.md").write_text("associative memory and spreading activation")
    m = mind()
    d = Driver(m, sleep=lambda _: None)
    d.add_sensor(FilesystemSensor(root))
    d.run(max_cycles=3)                 # no manual feed at all
    assert m.graph.nodes               # the world reached in and was encoded
    assert any("associative" in n.content for n in m.graph.nodes.values())


# --- sensorium hardening (R4 review P0/P1) --------------------------------- #
def test_filesystem_sensor_does_not_escape_root_via_hardlink():
    """R4 review P0: a hardlink inside root is a second name for an outside file
    that resolve() can't see through. It must not be read."""
    root, outside = _tmproot(), _tmproot()
    secret = outside / "secret.txt"
    secret.write_text("SECRET-OUTSIDE-ROOT-via-hardlink")
    try:
        os.link(secret, root / "hl.txt")        # hardlink (not symlink)
    except (OSError, NotImplementedError):
        return                                   # platform/fs without hardlinks: skip
    s = FilesystemSensor(root)
    texts = " ".join(t for t, _, _ in s.poll())
    assert "SECRET-OUTSIDE-ROOT" not in texts


def test_filesystem_sensor_skips_secret_named_files_even_with_allowed_suffix():
    root = _tmproot()
    (root / "credentials.txt").write_text("AKIA-not-to-be-read")
    (root / "db.secret.json").write_text("password: hunter2")
    (root / "notes.txt").write_text("a harmless note")
    s = FilesystemSensor(root)
    texts = " ".join(t for t, _, _ in s.poll())
    assert "harmless note" in texts
    assert "AKIA-not-to-be-read" not in texts and "hunter2" not in texts


def test_sensed_nodes_carry_external_provenance():
    """World-sensed content must be distinguishable from the agent's own thought in
    the graph (R4 review P0): the node records its source and external flag."""
    root = _tmproot()
    (root / "world.md").write_text("a fact from the world about geology")
    m = mind()
    d = Driver(m, sleep=lambda _: None)
    d.add_sensor(FilesystemSensor(root))
    d.run(max_cycles=3)
    sensed = [n for n in m.graph.nodes.values() if n.meta.get("source") == "filesystem"]
    assert sensed and all(n.meta.get("external") for n in sensed)


def test_seen_state_is_pruned_when_files_vanish():
    root = _tmproot()
    s = FilesystemSensor(root)
    for i in range(20):
        f = root / f"transient{i}.txt"
        f.write_text("x")
        s.poll()
        f.unlink()
        s.poll()
    assert len(s._seen) <= 1                      # deleted files don't accumulate


def test_per_poll_cap_round_robins_so_no_file_is_starved():
    root = _tmproot()
    for i in range(12):
        (root / f"f{i:02d}.txt").write_text(f"content {i}")
    s = FilesystemSensor(root, max_per_poll=4)
    ever = set()
    for _ in range(5):
        for _, _, payload in s.poll():
            ever.add(payload["path"])
    assert len(ever) == 12                        # all eventually sensed, none starved


# --- warm-tier persistence: a restart resumes mid-thought ------------------ #
def test_warm_streams_survive_save_and_load():
    a = mind()
    from meno.event import Event
    ev = Event(content="an unfinished thought about memory")
    ev.embedding = a.embed.embed(ev.content)
    sid = a.streams.route(ev)
    a.streams.active[sid].deferred = True
    a.streams.active[sid].node_ids = [1, 2]
    a.streams.suspend(sid)
    assert sid in a.streams.warm
    path = Path(tempfile.mkdtemp()) / "state.json"
    a.save(path)

    b = mind()
    assert not b.streams.warm
    b.load(path)
    assert sid in b.streams.warm                       # the suspended thought survived
    restored = b.streams.warm[sid]
    assert restored.deferred and restored.node_ids == [1, 2]
    assert restored.summary == a.streams.warm[sid].summary


def test_restart_resumes_a_suspended_impulse_through_the_evolved_graph():
    """Theory check: a suspended impulse persists; after a restart the heartbeat's
    interoceptive wake resurfaces it (its deferred pressure builds and crosses the
    line), so the agent returns to the unfinished thought it slept on — not just to
    the cold graph."""
    a = mind()
    from meno.event import Event
    ev = Event(content="a deferred line of thinking to return to")
    ev.embedding = a.embed.embed(ev.content)
    sid = a.streams.route(ev)
    a.streams.active[sid].deferred = True
    a.streams.suspend(sid)
    path = Path(tempfile.mkdtemp()) / "state.json"
    a.save(path)

    b = mind()
    b.load(path)
    n0 = len(b.bus.log)
    b.heartbeat()                                      # the quiet phase
    woke = [e for e in b.bus.log[n0:]
            if e.source == "initiative" and e.stream_id == sid]
    assert woke                                        # it resumed the suspended impulse


def test_warm_streams_skipped_on_embedder_dim_mismatch():
    """R4 review P1: warm centroids are hot-space embeddings. Restoring them under a
    different-dimensioned embedder would corrupt routing silently — better to wake
    from the cold graph alone than resume a half-thought in the wrong space."""
    from meno.event import Event
    a = Meno(config=Config(), embed=HashingEmbedding(dim=64), models=StubModelProvider(),
             workspace=tempfile.mkdtemp())
    ev = Event(content="a thought in 64-dim space")
    ev.embedding = a.embed.embed(ev.content)
    sid = a.streams.route(ev)
    a.streams.suspend(sid)
    path = Path(tempfile.mkdtemp()) / "state.json"
    a.save(path)

    b = Meno(config=Config(), embed=HashingEmbedding(dim=128), models=StubModelProvider(),
             workspace=tempfile.mkdtemp())
    b.load(path)
    assert not b.streams.warm                          # mismatched embedder -> warm tier skipped
