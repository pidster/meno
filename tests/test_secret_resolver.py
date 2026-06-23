"""Secret resolution (D31) — the formalised env-var-name -> value indirection that lives
in the composition root, NEVER the kernel or the mind.

Secrets are referenced by name in config and resolved here to values that live only in
the adapter object. The default is env-only (nothing in the home); a read-only dotenv
file is an explicit opt-in. The resolver never logs values and never writes them.
"""
import ast
import pathlib

import pytest

from meno_adapters.secrets import (DotenvBackend, EnvBackend, SecretResolver, env_resolver)


# --- env backend: the default, 12-factor ----------------------------------------- #
def test_env_backend_resolves_from_the_process_environment(monkeypatch):
    monkeypatch.setenv("MENO_TEST_TOKEN", "xoxb-from-env")
    assert env_resolver().resolve("MENO_TEST_TOKEN") == "xoxb-from-env"


def test_an_unset_or_empty_name_resolves_to_none(monkeypatch):
    monkeypatch.delenv("MENO_TEST_MISSING", raising=False)
    monkeypatch.setenv("MENO_TEST_EMPTY", "")           # empty is treated as absent
    r = env_resolver()
    assert r.resolve("MENO_TEST_MISSING") is None
    assert r.resolve("MENO_TEST_EMPTY") is None
    assert r.resolve(None) is None and r.resolve("") is None
    assert r.has("MENO_TEST_MISSING") is False


# --- dotenv backend: explicit, read-only, never written --------------------------- #
def test_dotenv_backend_reads_keys_and_ignores_comments_and_quotes(tmp_path):
    env = tmp_path / "secrets.env"
    env.write_text("# a comment\n"
                   'SLACK_BOT_TOKEN="xoxb-quoted"\n'
                   "export SLACK_APP_TOKEN=xapp-exported\n"
                   "BARE=plain\n"
                   "\n"
                   "NOTAKEYLINE\n")
    b = DotenvBackend(env)
    assert b.get("SLACK_BOT_TOKEN") == "xoxb-quoted"     # quotes stripped
    assert b.get("SLACK_APP_TOKEN") == "xapp-exported"   # `export ` prefix handled
    assert b.get("BARE") == "plain"
    assert b.get("ABSENT") is None


def test_dotenv_backend_is_inert_when_the_file_is_missing(tmp_path):
    assert DotenvBackend(tmp_path / "nope.env").get("ANY") is None   # no error, just nothing


def test_dotenv_backend_never_writes_the_file(tmp_path):
    path = tmp_path / "secrets.env"
    path.write_text("K=v\n")
    before = path.read_text()
    b = DotenvBackend(path)
    b.get("K"); b.get("MISSING")
    assert path.read_text() == before                    # read-only: untouched


# --- precedence: env wins over the file; chain is tried in order ------------------ #
def test_env_takes_precedence_over_the_dotenv_file(tmp_path, monkeypatch):
    env = tmp_path / "secrets.env"
    env.write_text("THE_TOKEN=from-file\n")
    monkeypatch.setenv("THE_TOKEN", "from-env")
    r = SecretResolver([EnvBackend(), DotenvBackend(env)])
    assert r.resolve("THE_TOKEN") == "from-env"          # env first wins
    # and the file is the fallback when env is unset
    monkeypatch.delenv("THE_TOKEN", raising=False)
    assert r.resolve("THE_TOKEN") == "from-file"


# --- it never leaks values (no value in repr; the seam can't print a secret) ------ #
def test_resolver_repr_never_contains_a_secret_value(tmp_path):
    env = tmp_path / "secrets.env"
    env.write_text("SECRET=super-secret-value\n")
    r = SecretResolver([DotenvBackend(env)])
    assert "super-secret-value" not in repr(r) and "backends=1" in repr(r)


# --- the adapter resolves its token THROUGH the resolver, not os.environ ---------- #
def test_slack_adapter_resolves_its_bot_token_via_the_resolver(monkeypatch):
    """No SLACK_BOT_TOKEN in the environment, but the resolver supplies it from a file —
    the adapter must build its client off the resolver, proving the indirection is real
    (this also requires slack_sdk; skip cleanly if the optional dep is absent)."""
    pytest.importorskip("slack_sdk")
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    from meno_adapters import SlackAdapter

    class FileOnly:                                     # a backend that only knows the token
        def get(self, name):
            return "xoxb-resolved-from-backend" if name == "SLACK_BOT_TOKEN" else None
    ad = SlackAdapter(channels=["C_meno"], bot_user_id="U_bot",
                      secrets=SecretResolver([FileOnly()]))
    assert ad.available is True                          # a client was built from the resolved token


def test_slack_adapter_without_a_resolved_token_is_inert(monkeypatch):
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    from meno_adapters import SlackAdapter
    ad = SlackAdapter(channels=["C_meno"])              # default env-only resolver, token unset
    assert ad.available is False and ad.poll() == []


# --- the resolver lives OUTSIDE the kernel: no meno/ module imports it ------------- #
def test_no_kernel_module_imports_the_secret_resolver():
    import meno
    kernel = pathlib.Path(meno.__file__).parent
    offenders = []
    for py in kernel.rglob("*.py"):
        for node in ast.walk(ast.parse(py.read_text())):
            mods = ([n.name for n in node.names] if isinstance(node, ast.Import)
                    else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
            if any((m or "").split(".")[0] == "meno_adapters" for m in mods):
                offenders.append(py.name)
    assert not offenders, f"kernel imports the adapter/secret layer: {offenders}"
