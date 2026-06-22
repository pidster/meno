"""Phase I0b — the instance home: meno init, the config loader, the egress policy,
and the home-bound daemon (D21/D22).

Offline and deterministic. The OCI image BUILD/RUN smoke is the one external
dependency (a container runtime + network) — flagged and skipped here, like R1's
"needs a model".
"""
import shutil
import tomllib
from pathlib import Path

import pytest

from meno.cli import main, run_instance
from meno.home import EgressPolicy, build_instance, init_home, load_config


# --- meno init: scaffold the home, and meno.toml parses via tomllib --------------- #
def test_init_scaffolds_the_home_tree(tmp_path):
    home = init_home(tmp_path / "inst", handle="meno-test")
    for d in ("substrate/snapshots", "library/dictionary", "skills/authored",
              "adapters", "journal/traces", "run"):
        assert (home / d).is_dir(), d
    assert (home / "meno.toml").exists()
    assert (home / ".gitignore").exists()
    # the library is seeded + the self-model exported
    assert (home / "library" / "index.json").exists()
    assert "You are a Meno" in (home / "library" / "self-model.md").read_text()


def test_meno_toml_parses_with_stdlib_tomllib(tmp_path):
    home = init_home(tmp_path / "inst", handle="meno-pid")
    with open(home / "meno.toml", "rb") as f:
        conf = tomllib.load(f)
    assert conf["instance"]["handle"] == "meno-pid"
    assert conf["cognition"]["provider"] == "stub"
    assert conf["egress"]["allow"] == []


def test_init_does_not_clobber_an_existing_meno_toml(tmp_path):
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text('[instance]\nhandle = "edited-by-operator"\n')
    init_home(home)                                  # re-init must not overwrite operator edits
    assert "edited-by-operator" in (home / "meno.toml").read_text()


def test_load_config_requires_a_meno_toml(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "empty")


# --- the egress policy: deny by default, allowlist gates outbound ----------------- #
def test_egress_denies_by_default_and_allows_only_listed_hosts():
    policy = EgressPolicy(allow=("slack.com", "*.slack.com"))
    assert policy.allows("slack.com")
    assert policy.allows("api.slack.com")            # wildcard
    assert not policy.allows("evil.example.com")
    assert not policy.allows("")
    with pytest.raises(PermissionError):
        policy.check("evil.example.com")
    policy.check("slack.com")                        # allowed -> no raise


def test_empty_allowlist_denies_everything():
    assert not EgressPolicy(allow=()).allows("slack.com")


def _egress_driver(allow, ad):
    import tempfile
    from meno import Config, Driver, Meno, StubModelProvider
    mind = Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_egress_"))
    driver = Driver(mind, sleep=lambda _: None, egress=EgressPolicy(allow=allow))
    driver.add_adapter(ad)
    return mind, driver


def test_egress_gates_the_adapters_declared_reach_not_just_a_payload_field():
    """The boundary checks the ADAPTER's declared hosts — so an adapter that reaches
    the network is refused even when the (mind-authored) intent names no host. That's
    the real D21 guard: the sender can't bypass it by omitting `host`."""
    from meno_adapters import LoopbackAdapter
    ad = LoopbackAdapter(action="post")
    ad.hosts = ("evil.example.com",)                  # the adapter actually reaches here
    ran = []
    orig = ad.deliver
    ad.deliver = lambda p: (ran.append(p), orig(p))[1]
    mind, driver = _egress_driver(("slack.com",), ad)
    mind.outbox.put({"action": "post", "data": "x"})  # NO host field — still refused
    assert driver.drain_outbox_once() is False
    assert ran == [] and driver.egress_denied == 1    # adapter never ran; counted distinctly


def test_egress_allows_an_adapter_whose_declared_hosts_clear_the_list():
    from meno_adapters import LoopbackAdapter
    ad = LoopbackAdapter(action="post")
    ad.hosts = ("api.slack.com",)
    ran = []
    orig = ad.deliver
    ad.deliver = lambda p: (ran.append(p), orig(p))[1]
    mind, driver = _egress_driver(("*.slack.com",), ad)
    mind.outbox.put({"action": "post", "data": "ok"})
    driver.drain_outbox_once()
    assert ran and driver.egress_denied == 0          # allowed reach -> delivered


def test_egress_policy_loads_from_config(tmp_path):
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text(
        '[egress]\nallow = ["slack.com", "*.slack.com"]\n')
    inst = build_instance(home)
    assert inst.egress.allows("api.slack.com") and not inst.egress.allows("nope.com")


# --- build_instance: binds offline, applies config overrides ---------------------- #
def test_build_instance_is_offline_and_applies_config_overrides(tmp_path):
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text(
        '[cognition]\nprovider = "stub"\n[embeddings]\nkind = "hashing"\n'
        '[driver]\ndream_every = 3\n[config]\nbus_log_max = 1234\n')
    inst = build_instance(home)
    assert inst.mind.models.name == "stub"           # offline by default
    assert inst.mind.cfg.bus_log_max == 1234          # [config] override applied
    assert inst.driver.dream_every == 3               # [driver] setting applied


def test_anthropic_requested_without_a_key_falls_back_to_stub(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text('[cognition]\nprovider = "anthropic"\n')
    inst = build_instance(home)                      # no key -> safe offline fallback, not a crash
    assert inst.mind.models.name == "stub"


def test_a_typo_or_bad_type_in_meno_toml_is_a_loud_error(tmp_path):
    home = init_home(tmp_path / "inst")
    (home / "meno.toml").write_text('[config]\nbus_log_mx = 4096\n')   # typo'd key
    with pytest.raises(ValueError, match="unknown key"):
        build_instance(home)
    (home / "meno.toml").write_text('[driver]\ndream_every = "eight"\n')  # non-numeric
    with pytest.raises(ValueError, match="must be an integer"):
        build_instance(home)


def test_two_daemons_cannot_both_hold_one_home(tmp_path):
    home = init_home(tmp_path / "inst")
    a, b = build_instance(home), build_instance(home)
    assert a.acquire_lock() is True
    try:
        assert b.acquire_lock() is False             # the substrate is single-writer
    finally:
        a.release_lock()
    assert b.acquire_lock() is True                  # released -> available again
    b.release_lock()


# --- the daemon: status.json + sleep-not-amnesia (D12) ---------------------------- #
def test_run_writes_status_json_with_telemetry(tmp_path):
    home = init_home(tmp_path / "inst", handle="meno-x")
    inst = run_instance(home, max_cycles=6, status_every=2, sleep=lambda _: None,
                        feed=["memory is reconstructed at recall"])
    import json
    data = json.loads(inst.status_path.read_text())
    assert data["handle"] == "meno-x" and data["cycles"] >= 6
    assert "cognition_real_fraction" in data and "nodes" in data


def test_restart_resumes_the_substrate_sleep_not_amnesia(tmp_path):
    home = init_home(tmp_path / "inst")
    run_instance(home, max_cycles=3, sleep=lambda _: None,
                 feed=["otters raft together while sleeping",
                       "kelp anchors the floating raft"])
    assert (home / "substrate" / "graph.json").exists()
    # a fresh process binds the SAME home and wakes with the substrate intact
    woken = build_instance(home)
    assert len(woken.mind.graph.nodes) >= 2           # the memories carried across
    contents = {n.content for n in woken.mind.graph.nodes.values()}
    assert any("otters" in c for c in contents)


# --- the CLI entrypoint: init / run / status ------------------------------------- #
def test_cli_init_run_status_roundtrip(tmp_path, capsys):
    home = tmp_path / "inst"
    assert main(["init", str(home), "--handle", "meno-cli"]) == 0
    assert (home / "meno.toml").exists()
    assert main(["run", str(home), "--cycles", "2"]) == 0
    assert main(["status", str(home)]) == 0
    out = capsys.readouterr().out
    assert "meno-cli" in out                          # status.json content printed


# --- the OCI image: smoke is the external-dependency gate (skip-not-fail) ---------- #
def test_containerfile_declares_the_safety_boundary():
    cf = Path("Containerfile").read_text()
    assert "USER meno" in cf and "VOLUME" in cf       # non-root + the mounted-home boundary
    assert "ENTRYPOINT" in cf and "meno" in cf


@pytest.mark.skipif(not (shutil.which("podman") or shutil.which("docker")),
                    reason="no container runtime — image build/run smoke is deferred (D21)")
def test_image_builds_and_runs__deferred():
    pytest.skip("image build/run smoke requires a container runtime + network (deferred, D21)")
