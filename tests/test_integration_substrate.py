"""Phase I0a — the integration substrate (adapter seam; no network).

Proves the seam by which the world reaches the mind, that the efferent half runs OFF
the mind thread, that the structured delivery result supports I2's gating, and that
network stays out of meno/.
"""
import ast
import pathlib
import sys
import tempfile
import threading
import time

from meno import Config, Driver, Meno, StubModelProvider
from meno.event import Event, Kind
from meno_adapters import Adapter, LoopbackAdapter
from meno_adapters.base import DeliveryResult


def _mind():
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_i0a_"))


def _noop_sleep(_):
    pass


def _outbound(action="echo", **data):
    """An INTENT explicitly marked egress (closed-world: only marked intents relay)."""
    return Event(content=f"intent: {action}", kind=Kind.INTENT, source="test",
                 payload={"action": action, "egress": True, **data})


# --- afferent: a percept enters THROUGH the adapter's poll, one guarded path ------ #
def test_afferent_percept_enters_through_the_adapter_poll_seam():
    mind = _mind()
    driver = Driver(mind, sleep=_noop_sleep)
    driver.add_adapter(LoopbackAdapter(afferent_percept="hello from the channel"))
    driver.run(max_cycles=1)                        # the driver polls the adapter, guarded
    assert any(e.source == "loopback" and "channel" in e.content for e in mind.bus.log)


def test_a_flaky_adapter_poll_does_not_kill_the_loop():
    class Flaky(Adapter):
        name = "flaky"
        def poll(self): raise RuntimeError("channel down")
    mind = _mind()
    driver = Driver(mind, sleep=_noop_sleep)
    driver.add_adapter(Flaky())
    driver.run(max_cycles=2)                        # survives; the failure is recorded, not fatal
    assert driver.errors >= 1 and "flaky" in (driver.last_error or "").lower()


# --- efferent hand-off: the mind thread enqueues, it does NOT run the action ------ #
def test_outbound_intent_is_relayed_to_the_outbox_not_executed_on_the_mind_thread():
    mind = _mind()
    mind.submit(_outbound("echo", data="hi"))
    mind.run_until_quiescent()
    assert mind.outbox.qsize() == 1                # relayed, not run
    payload = mind.outbox.get_nowait()
    assert payload["action"] == "echo" and payload["data"] == "hi"
    assert not any(e.source == "loopback" for e in mind.bus.log)   # nothing delivered on the mind thread


def test_unmarked_and_local_intents_are_not_relayed_outbound():
    """Closed-world: only egress-marked intents relay. A lookup (local) and an
    unmarked intent must NOT be handed to the outbox — so a future local action can't
    be mis-relayed-and-dropped."""
    mind = _mind()
    mind.submit(Event(content="intent: lookup", kind=Kind.INTENT, payload={"action": "lookup", "key": "memory"}))
    mind.submit(Event(content="intent: tool", kind=Kind.INTENT, payload={"action": "some_future_tool"}))
    mind.run_until_quiescent()
    assert mind.outbox.qsize() == 0


# --- the structured result gives I2 its gating seam (delivered/refused/pending) --- #
def test_drain_outbox_once_delivers_and_feeds_back():
    mind = _mind()
    driver = Driver(mind, sleep=_noop_sleep)
    driver.add_adapter(LoopbackAdapter(action="echo"))
    mind.outbox.put({"action": "echo", "data": "ping"})
    assert driver.drain_outbox_once() is True
    driver.run(max_cycles=1)
    fb = [e for e in mind.bus.log if e.source == "loopback"]
    assert fb and "ping" in fb[0].content and fb[0].kind == Kind.FEEDBACK


def test_refused_delivery_feeds_back_a_refusal_with_its_reason():
    mind = _mind()
    driver = Driver(mind, sleep=_noop_sleep)
    driver.add_adapter(LoopbackAdapter(action="post", status="refused", reason="scope"))
    mind.outbox.put({"action": "post", "data": "nope"})
    driver.drain_outbox_once()
    driver.run(max_cycles=1)
    fb = [e for e in mind.bus.log if e.kind == Kind.FEEDBACK and e.payload.get("refused")]
    assert fb and fb[0].payload["refused"] == "scope"     # the mind feels 'I was blocked', with why


def test_unhandled_outbound_intent_drops_cleanly_and_feeds_a_miss():
    mind = _mind()
    driver = Driver(mind, sleep=_noop_sleep)
    driver.add_adapter(LoopbackAdapter(action="echo"))     # handles echo, NOT "post"
    mind.outbox.put({"action": "post", "data": "x"})
    assert driver.drain_outbox_once() is False             # no adapter handled it
    assert driver.dropped_outbound == 1                    # counted, not silent
    driver.run(max_cycles=1)
    assert any("no adapter" in e.content for e in mind.bus.log if e.kind == Kind.FEEDBACK)


# --- run() can act outward too (the outbox is drained inline when no worker) ------ #
def test_run_mode_drains_the_outbox_inline():
    mind = _mind()
    driver = Driver(mind, sleep=_noop_sleep)
    driver.add_adapter(LoopbackAdapter(action="echo"))
    mind.submit(_outbound("echo", data="from-run"))        # relayed to outbox during the cycle
    driver.run(max_cycles=2)                               # step() drains it inline (no bg worker)
    assert any(e.source == "loopback" and "from-run" in e.content for e in mind.bus.log)


# --- the load-bearing property: the slow deliver runs off the mind thread --------- #
def test_outbound_delivery_runs_off_the_mind_thread_and_does_not_block_it():
    gate = threading.Event()
    ad = LoopbackAdapter(action="echo", gate=gate)         # deliver() blocks until gate is set
    mind = _mind()
    driver = Driver(mind, sleep=time.sleep, idle_backoff=0.001, max_backoff=0.01)
    driver.add_adapter(ad)
    driver.start()
    try:
        mind.outbox.put({"action": "echo", "data": "slow"})
        assert ad.started.wait(timeout=2.0)                # the worker began delivery (off-thread)
        c0 = driver.cycles
        driver.feed("a percept while delivery is blocked", source="probe")
        # the mind loop must keep TURNING while deliver is gated (proof of non-blocking)
        deadline = time.time() + 2.0
        while time.time() < deadline and driver.cycles < c0 + 2:
            time.sleep(0.005)
        assert driver.cycles >= c0 + 2, "the mind loop was blocked by the slow outbound deliver"
    finally:
        gate.set()                                         # let deliver finish
        driver.stop()
    # after join (no concurrent mutation): the probe was processed, deliver ran off-thread
    assert any(e.source == "probe" for e in mind.bus.log)
    assert ad.delivered and ad.delivered[0][1] == "meno-outbound"


def test_stop_reports_false_when_an_outbound_deliver_is_still_blocked():
    gate = threading.Event()
    ad = LoopbackAdapter(action="echo", gate=gate)
    mind = _mind()
    driver = Driver(mind, sleep=time.sleep, idle_backoff=0.001, max_backoff=0.01)
    driver.add_adapter(ad)
    driver.start()
    try:
        mind.outbox.put({"action": "echo", "data": "stuck"})
        assert ad.started.wait(timeout=2.0)                # worker is now blocked in deliver
        stopped = driver.stop(timeout=0.2)                 # join times out — be honest
        assert stopped is False                            # never claim free while a socket is held
    finally:
        gate.set()
        driver.stop()


# --- kernel purity: no integration/channel network leaks into meno/ --------------- #
# Allowlist (robust vs any future channel lib): stdlib + first-party meno + the
# intentional cognition/embedding extras. The kernel MAY call the cognition API
# (real thought) and the embedder; it may NOT import a channel/transport SDK — that
# is meno_adapters. Recursive, so a future meno/ subpackage is covered too.
_ALLOWED_THIRD_PARTY = {"anthropic", "sentence_transformers"}


def _imported_modules(path: pathlib.Path):
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            for n in node.names:
                yield n.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_kernel_imports_only_stdlib_cognition_and_first_party():
    import meno
    kernel = pathlib.Path(meno.__file__).parent
    allowed = set(sys.stdlib_module_names) | {"meno"} | _ALLOWED_THIRD_PARTY
    offenders = []
    for py in kernel.rglob("*.py"):
        for mod in _imported_modules(py):
            if mod not in allowed:
                offenders.append((py.name, mod))
    assert not offenders, f"non-allowed (channel/network?) imports in the kernel: {offenders}"


def test_adapter_layer_is_importable_and_separate_from_the_kernel():
    import meno
    import meno_adapters
    assert pathlib.Path(meno_adapters.__file__).parent != pathlib.Path(meno.__file__).parent
    assert issubclass(LoopbackAdapter, Adapter)
    # every outward decision is felt — delivered, refused, or dry-run (D35: no pending)
    assert DeliveryResult("delivered", "x").feeds_back and DeliveryResult("dry-run", "y").feeds_back
