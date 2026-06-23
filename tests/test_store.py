"""The substrate store seam (D34): the backend the persistent graph lives in.

The file store is the default and the only backend that ships; it round-trips the
substrate (sleep, not amnesia — D12). A non-file backend is an honest not-implemented
seam: it fails loudly with a pointer, never a silent no-op that looks like it persisted.
"""
import tempfile

import pytest

from meno import Config, Meno, StubModelProvider
from meno.store import FileStore, Store, make_store


def _mind(ws):
    return Meno(config=Config(), models=StubModelProvider(), workspace=ws)


# --- make_store: selection + the honest not-implemented seam ---------------------- #
def test_default_backend_is_a_file_store(tmp_path):
    store = make_store({}, tmp_path)
    assert isinstance(store, Store) and isinstance(store, FileStore)
    assert store.path == tmp_path / "substrate" / "graph.json"


def test_explicit_file_backend(tmp_path):
    store = make_store({"storage": {"backend": "file"}}, tmp_path)
    assert isinstance(store, FileStore)


def test_an_unimplemented_backend_fails_loudly_not_silently(tmp_path):
    with pytest.raises(NotImplementedError, match="not implemented"):
        make_store({"storage": {"backend": "surreal"}}, tmp_path)


# --- the file store round-trips the substrate (sleep, not amnesia) ---------------- #
def test_file_store_saves_and_restores_the_substrate(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    mind = _mind(ws)
    mind.feed("otters raft together while sleeping", source="test")
    mind.run_until_quiescent()
    store = FileStore(tmp_path / "substrate" / "graph.json")
    store.save(mind)
    assert store.describe().startswith("file:")

    woken = _mind(tmp_path / "ws2")
    assert store.load(woken) is True                  # a prior substrate was restored
    assert len(woken.graph.nodes) >= 1
    assert any("otters" in n.content for n in woken.graph.nodes.values())


def test_file_store_load_is_a_noop_on_a_fresh_home(tmp_path):
    store = FileStore(tmp_path / "substrate" / "graph.json")
    assert store.load(_mind(tmp_path / "ws")) is False   # nothing to restore yet


# --- it is wired through the instance (build restores; save persists) ------------- #
def test_build_instance_uses_the_store_and_a_surreal_backend_errors_at_build(tmp_path):
    from meno.home import build_instance, init_home
    home = init_home(tmp_path / "inst")
    inst = build_instance(home)
    assert isinstance(inst.store, FileStore)          # the default backend is wired in

    (home / "meno.toml").write_text('[storage]\nbackend = "surreal"\n')
    with pytest.raises(NotImplementedError):
        build_instance(home)                          # selecting an unbuilt backend is a loud error
