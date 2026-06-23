"""Phase K3 — external knowledge authorities.

A Library miss falls through to a network authority (off-thread, egress-gated); the
result re-enters as a REFERENCE (read, never encoded as experience) and is curated
into the Library so a repeat lookup is a local hit. Offline/deterministic with a fake
authority; the real network/MCP path is host+egress gated (deferred).
"""
import tempfile

from meno import Config, Driver, Meno, StubModelProvider
from meno.event import Event, Kind
from meno.home import EgressPolicy
from meno.processors import Effector
from meno_adapters import KnowledgeAdapter
from meno_adapters.base import DeliveryResult


def _meno():
    return Meno(config=Config(), models=StubModelProvider(),
                workspace=tempfile.mkdtemp(prefix="meno_k3_"))


class FakeAuthority:
    def __init__(self, answers):
        self.answers = answers
        self.calls = []

    def lookup(self, query):
        self.calls.append(query)
        for term, body in self.answers.items():
            if term in query.lower():
                return body
        return None


def _lookup_intent(key):
    return Event(content=f"intent: lookup {key}", kind=Kind.INTENT,
                 payload={"action": "lookup", "key": key})


# --- a Library miss routes OUTWARD to a knowledge authority ---------------------- #
def test_library_miss_emits_an_egress_gated_knowledge_intent():
    m = _meno()                                       # "entropy" is not in the seed library
    out = Effector().run(_lookup_intent("what is entropy"), m)[0]
    assert out.kind == Kind.INTENT and out.payload["action"] == "knowledge"
    assert out.payload["egress"] is True              # relayed outbound, behind the boundary
    assert out.payload["curate_key"] == "def:entropy"  # the key it will be curated under


def test_a_library_hit_still_resolves_locally_without_going_outward():
    m = _meno()                                       # "memory" IS in the seed library
    out = Effector().run(_lookup_intent("what is memory"), m)[0]
    assert out.kind == Kind.REFERENCE and out.payload["hit"] is True
    assert out.content == m.library.get("def:memory").body


# --- the KnowledgeAdapter resolves against the authority ------------------------- #
def test_knowledge_adapter_returns_a_reference_on_a_hit():
    ad = KnowledgeAdapter(client=FakeAuthority({"entropy": "a measure of disorder"}),
                          hosts=("api.example.com",), kind="web")
    res = ad.deliver({"action": "knowledge", "key": "what is entropy", "curate_key": "def:entropy"})
    assert res.status == "delivered"
    assert res.reference == {"key": "def:entropy", "body": "a measure of disorder",
                             "source": "authority:web:api.example.com"}   # provenance names the host


def test_knowledge_adapter_miss_and_unavailable_are_honest_refusals():
    ad = KnowledgeAdapter(client=FakeAuthority({}), hosts=("api.example.com",))
    miss = ad.deliver({"action": "knowledge", "key": "no such term"})
    assert miss.status == "refused" and miss.reason == "miss" and miss.reference is None
    inert = KnowledgeAdapter(hosts=("api.example.com",))   # no client
    assert inert.available is False
    assert inert.deliver({"action": "knowledge", "key": "x"}).reason == "unavailable"


# --- egress gates the authority before any call --------------------------------- #
def test_egress_refuses_a_non_allowlisted_authority_before_the_call():
    m = _meno()
    auth = FakeAuthority({"entropy": "disorder"})
    driver = Driver(m, sleep=lambda _: None, egress=EgressPolicy(allow=()))   # deny all
    driver.add_adapter(KnowledgeAdapter(client=auth, hosts=("api.example.com",)))
    m.outbox.put({"action": "knowledge", "key": "entropy", "curate_key": "def:entropy", "egress": True})
    assert driver.drain_outbox_once() is False
    assert driver.egress_denied == 1 and auth.calls == []   # the authority was never reached


# --- end to end: miss -> authority -> curated reference, no substrate contamination - #
def test_a_looked_up_fact_re_enters_as_reference_curated_not_encoded():
    m = _meno()
    auth = FakeAuthority({"entropy": "entropy is a measure of disorder in a system"})
    driver = Driver(m, sleep=lambda _: None, dream_every=0,
                    egress=EgressPolicy(allow=("api.example.com",)))
    driver.add_adapter(KnowledgeAdapter(client=auth, hosts=("api.example.com",), kind="web"))

    m.bus.publish(_lookup_intent("what is entropy"))
    driver.run(max_cycles=3)        # lookup miss -> knowledge intent -> outbox -> authority -> curate

    assert auth.calls == ["what is entropy"]
    # curated into the Library -> a repeat lookup is now a LOCAL hit
    curated = m.library.get("def:entropy")
    assert curated is not None and "disorder" in curated.body
    assert curated.source == "authority:web:api.example.com"
    # the looked-up fact did NOT become a graph node — reference is not experience
    assert not any("disorder" in n.content for n in m.graph.nodes.values())
    # the repeat lookup resolves locally, no second outward call
    out = Effector().run(_lookup_intent("entropy"), m)[0]
    assert out.kind == Kind.REFERENCE and out.payload["hit"] is True
    assert auth.calls == ["what is entropy"]          # the authority was not consulted again


def test_no_authority_configured_is_an_honest_miss_fed_back():
    m = _meno()
    driver = Driver(m, sleep=lambda _: None, dream_every=0)   # no knowledge adapter
    m.bus.publish(_lookup_intent("what is entropy"))
    driver.run(max_cycles=3)                           # nothing handles "knowledge"
    assert driver.dropped_outbound == 1
    assert any("no adapter" in e.content for e in m.bus.log if e.kind == Kind.FEEDBACK)


# --- every outbound decision is durably audited (P0: "audited like any outbound call") -- #
def test_every_outbound_decision_is_audited(tmp_path):
    m = _meno()
    auth = FakeAuthority({"entropy": "a measure of disorder"})
    audit = tmp_path / "outbound.jsonl"
    driver = Driver(m, sleep=lambda _: None, audit_path=audit,
                    egress=EgressPolicy(allow=("api.example.com",)))
    driver.add_adapter(KnowledgeAdapter(client=auth, hosts=("api.example.com",), kind="web"))
    m.outbox.put({"action": "knowledge", "key": "what is entropy",
                  "curate_key": "def:entropy", "egress": True})
    driver.drain_outbox_once()
    import json
    rec = json.loads(audit.read_text().strip())
    assert rec["adapter"] == "knowledge" and rec["outcome"] == "delivered" and "ts" in rec


def test_an_egress_denial_is_audited(tmp_path):
    m = _meno()
    audit = tmp_path / "outbound.jsonl"
    driver = Driver(m, sleep=lambda _: None, audit_path=audit, egress=EgressPolicy(allow=()))
    driver.add_adapter(KnowledgeAdapter(client=FakeAuthority({"x": "y"}), hosts=("api.example.com",)))
    m.outbox.put({"action": "knowledge", "key": "x", "curate_key": "def:x", "egress": True})
    driver.drain_outbox_once()
    import json
    rec = json.loads(audit.read_text().strip())
    assert rec["outcome"] == "refused" and rec["reason"] == "egress"   # the highest-value security event


# --- a refused lookup feeds back a reason (cognition feels the block) ------------ #
def test_a_refused_lookup_feeds_back_its_reason():
    m = _meno()
    driver = Driver(m, sleep=lambda _: None, dream_every=0,
                    egress=EgressPolicy(allow=("api.example.com",)))
    driver.add_adapter(KnowledgeAdapter(client=FakeAuthority({}),   # always misses
                                        hosts=("api.example.com",)))
    m.bus.publish(_lookup_intent("what is entropy"))
    driver.run(max_cycles=3)
    fb = [e for e in m.bus.log if e.kind == Kind.FEEDBACK and e.payload.get("refused") == "miss"]
    assert fb                                          # the mind learns the lookup found nothing


# --- the K3 fall-through neither bypasses nor inflates the supplantation guard ---- #
def test_a_network_fallthrough_does_not_inflate_supplantation():
    m = _meno()
    # a discharge that the substrate could NOT serve -> a legitimate lookup; resolving
    # the miss via the network must not count as supplantation (the opposite of it).
    m.curiosities.register("what is the definition of entropy", source="bottom-up")
    m._discharge_curiosity()
    assert m.lookup_tel["lookups"] == 1                # the decision was counted (at discharge)
    assert m.lookup_tel["supplanted"] == 0 and m.supplantation_ratio == 0.0
    # the Effector's miss fall-through (K3) does not touch the supplantation telemetry
    Effector().run(_lookup_intent("what is the definition of entropy"), m)
    assert m.lookup_tel["supplanted"] == 0            # unchanged — a miss isn't supplantation


# --- curation-key round-trip survives phrasing variation ------------------------- #
def test_a_curated_fact_is_hit_by_a_differently_phrased_repeat():
    m = _meno()
    auth = FakeAuthority({"entropy": "a measure of disorder"})
    driver = Driver(m, sleep=lambda _: None, dream_every=0,
                    egress=EgressPolicy(allow=("api.example.com",)))
    driver.add_adapter(KnowledgeAdapter(client=auth, hosts=("api.example.com",)))
    m.bus.publish(_lookup_intent("what does entropy mean"))    # curates under def:entropy
    driver.run(max_cycles=3)
    assert m.library.get("def:entropy") is not None
    # a DIFFERENTLY phrased repeat resolves locally — no second authority call
    out = Effector().run(_lookup_intent("what is entropy"), m)[0]
    assert out.kind == Kind.REFERENCE and out.payload["hit"] is True
    assert auth.calls == ["what does entropy mean"]


# --- a hostile authority body is redacted + bounded before it is curated --------- #
def test_curated_body_is_redacted_and_bounded():
    ad = KnowledgeAdapter(client=FakeAuthority({"x": "the api_key=SUPERSECRET12345 and " + "z" * 5000}),
                          hosts=("api.example.com",), max_chars=100)
    res = ad.deliver({"action": "knowledge", "key": "x", "curate_key": "def:x"})
    assert "SUPERSECRET12345" not in res.reference["body"]      # secret redacted
    assert len(res.reference["body"]) <= 100                    # bounded


# --- the Library is capped; authority-curated entries evict before seeds ---------- #
def test_library_is_capped_evicting_authority_entries_before_seeds():
    from meno import Library, Reference
    lib = Library(max_references=3)
    lib.put(Reference(key="def:a", body="A", source="authority:web:h", kind="reference"))
    lib.put(Reference(key="def:b", body="B", source="authority:web:h", kind="reference"))
    lib.put(Reference(key="seed:keep", body="protected", source="seed:dictionary", kind="definition"))
    lib.put(Reference(key="def:c", body="C", source="authority:web:h", kind="reference"))  # over cap
    assert lib.evicted == 1
    assert lib.get("def:a") is None                   # the oldest authority entry evicted
    assert lib.get("seed:keep") is not None           # the operator seed is protected
