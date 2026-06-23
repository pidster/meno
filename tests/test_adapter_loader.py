"""The config-driven adapter loader: `meno run` attaches the channels/authorities an
instance's adapters/*.toml enables, while the kernel stays adapter-blind.
"""
import ast
import pathlib

from meno.home import build_instance, init_home
from meno_adapters.cli import main as meno_main
from meno_adapters.loader import load_adapters


def test_disabled_by_default_attaches_no_adapters(tmp_path):
    home = init_home(tmp_path / "inst")
    inst = build_instance(home)
    assert load_adapters(inst) == []                 # init scaffolds everything OFF
    assert inst.driver.adapters == []


def test_enabling_slack_and_knowledge_attaches_them(tmp_path):
    home = init_home(tmp_path / "inst")
    (home / "adapters" / "slack.toml").write_text(
        '[afferent]\nenabled = true\nchannels = ["C_MENO"]\n'
        '[efferent]\nenabled = true\npost_channels = ["C_MENO"]\nconfirm = true\nrate = "3/min"\n')
    (home / "adapters" / "knowledge.toml").write_text(
        'enabled = true\nkind = "web"\nhosts = ["api.example.com"]\n')
    inst = build_instance(home)
    names = load_adapters(inst)
    assert set(names) == {"slack", "knowledge"}
    by = {a.name: a for a in inst.driver.adapters}
    # the efferent gate config flowed through
    assert by["slack"].enabled and by["slack"].post_channels == ("C_MENO",) and by["slack"].rate_per_min == 3
    assert by["knowledge"].hosts == ("api.example.com",)
    # egress is handed to each adapter by the driver (enforced on its send paths)
    assert by["slack"].egress is inst.egress and by["knowledge"].egress is inst.egress


def test_sense_only_slack_does_not_arm_posting(tmp_path):
    home = init_home(tmp_path / "inst")
    (home / "adapters" / "slack.toml").write_text(
        '[afferent]\nenabled = true\nchannels = ["C_MENO"]\n[efferent]\nenabled = false\n')
    inst = build_instance(home)
    load_adapters(inst)
    slack = inst.driver.adapters[0]
    assert slack.channels == ("C_MENO",) and slack.enabled is False   # listens, cannot post


def test_meno_run_drives_with_configured_adapters(tmp_path, capsys):
    home = tmp_path / "inst"
    meno_main(["init", str(home)])
    (home / "adapters" / "knowledge.toml").write_text(
        'enabled = true\nkind = "web"\nhosts = ["api.example.com"]\n')
    assert meno_main(["run", str(home), "--cycles", "1"]) == 0
    assert "knowledge" in capsys.readouterr().out     # the loader reported the attached adapter


# --- the kernel stays adapter-blind: no meno/ module imports meno_adapters -------- #
def test_no_kernel_module_imports_the_adapter_layer():
    import meno
    kernel = pathlib.Path(meno.__file__).parent
    offenders = []
    for py in kernel.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            mods = ([n.name for n in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            if any((m or "").split(".")[0] == "meno_adapters" for m in mods):
                offenders.append(py.name)
    assert not offenders, f"kernel modules import the adapter layer: {offenders}"
