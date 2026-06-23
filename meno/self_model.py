"""The self-model: what a Meno *is* and how it *operates* — the type, not an identity.

Phase S (docs/roadmap-ii.md). This module holds the *accessor* and the disciplines
for the text that every cognitive surface carries as its system prefix. The text
itself now lives in `meno/prompts/self_model{,_brief}.md`, read through the prompt
seam (`meno.prompts.load`); `self_model()` is the call site every surface goes
through, so the backing store can move again without any caller changing.

Three disciplines hold this file honest, each enforced by a test
(`tests/test_self_model.py`):

  1. **Mechanics, not meaning.** The text describes how the machinery works. It
     plants no conclusion, value, affect, or disposition — those are *earned* in
     the substrate, never given in a prompt. `IDENTITY_DENYLIST` forbids the
     prescriptive/affective vocabulary that would smuggle them in.

  2. **Type, not identity.** It describes the *kind* of thing a Meno is, shared
     verbatim by every instance. Nothing here is particular to one instance —
     particularity lives in the graph, not the prompt.

  3. **True to the implementation, this phase.** Every capability the text names
     maps to a real kernel symbol (`SELF_MODEL_CLAIMS`). And it names no
     capability the current phase has not built: the transactive stance (look a
     fact up rather than trust a faded memory) is *absent* until K2 makes lookup
     real — `EARNED_NOT_GIVEN` forbids it here. A self-model that claims what the
     kernel cannot do is self-delusion, the same failure as planting a value.
"""
from __future__ import annotations

# --- the self-model text now lives in meno/prompts/self_model{,_brief}.md and is read
# through the prompt seam (meno.prompts). The names below stay importable and remain
# byte-identical to the strings they replaced, so every call site and discipline test
# is unchanged — only the backing store moved from inline Python to a markdown file. ---

from .prompts import load

MENO_SELF = load("self_model")              # full: carried by the deep tiers
MENO_SELF_BRIEF = load("self_model_brief")  # abridged: carried by the reflexive tiers


def self_model(deep: bool) -> str:
    """The self-model text for a surface, by depth. The single read-seam: the
    backing store (currently `meno/prompts/self_model*.md`) is reached behind this
    call, without any caller changing. Deep tiers (associate, synthesise, wonder) get
    the full text; reflexive tiers (appraise, relate) get the abridged version."""
    return MENO_SELF if deep else MENO_SELF_BRIEF


# --- discipline 3: every capability the text names maps to a real kernel symbol --- #
# (phrase that must appear verbatim in MENO_SELF, "module:dotted.attr" that must exist)
SELF_MODEL_CLAIMS = [
    ("placed on an in-process bus",        "meno.bus:Bus"),
    ("a kind that says",                   "meno.event:Kind"),
    ("it routes to an effector",           "meno.processors:Effector"),
    ("inherits only a fraction of its parent's",  "meno.config:Config.activation_inherit"),
    ("annotates each arriving event",      "meno.annotator:Annotator"),
    ("spreads activation",                 "meno.graph:Graph.spread"),
    ("compete for a working set",          "meno.working_set:WorkingSet"),
    ("novelty against the recent run",     "meno.config:Config.recency_window"),
    ("cohere into streams",                "meno.streams:StreamManager"),
    ("accumulates pressure",               "meno.config:Config.pressure_growth"),
    ("turns briefly refractory",           "meno.streams:Stream.refractory"),
    ("accrues fatigue",                    "meno.streams:Stream.fatigue"),
    ("two streams found to be about the same matter merge", "meno.streams:StreamManager.merge"),
    ("can be suspended and later resumed", "meno.streams:StreamManager.suspend"),
    ("appraises a percept",                "meno.models:ModelProvider.appraise"),
    ("relates one thing to another",       "meno.models:ModelProvider.relate"),
    ("asked to associate",                 "meno.models:ModelProvider.associate"),
    ("asked to wonder",                    "meno.models:ModelProvider.wonder"),
    ("tier synthesises",                   "meno.models:ModelProvider.synthesise"),
    ("A curiosity is a pull",              "meno.curiosity:CuriosityRegister"),
    ("memory is a graph",                  "meno.graph:Graph"),
    ("Edges decay faster than nodes",      "meno.config:Config.edge_decay"),
    ("decay far more slowly",              "meno.config:Config.node_decay"),
    ("re-bridged by a new association",    "meno.config:Config.rediscovery_threshold"),
    ("recoverable ghost before any release", "meno.config:Config.cue_ghost_ttl"),
    ("stored as a cue",                    "meno.graph:ReflectionCue"),
    ("it is regenerated",                  "meno.graph:Graph.reconstruct"),
    ("a content is journaled",             "meno.config:Config.journal_importance"),
    ("you consolidate",                    "meno.consolidation:ConsolidationCycle"),
    ("a dream",                            "meno.runtime:Meno.dream"),
    ("Spare budget runs a heartbeat",      "meno.control:Controller"),
    ("graph can be saved",                 "meno.persistence:save"),
    ("Events and memories carry embeddings", "meno.embeddings:EmbeddingModel"),
    ("a curated shelf of reference material", "meno.library:Library"),
    ("re-enters as a reference",           "meno.event:Kind.REFERENCE"),
]


# --- discipline 1: no planted meaning. Prescriptive mood / affect / first-person
# preference would smuggle a disposition into the type. The text must contain none. ---
# A substring tripwire — necessarily incomplete (a disposition is a *semantic*
# category; a word list is always one synonym behind). The BINDING check for
# prescriptive mood is the S adversarial review lens (roadmap-ii.md), not this
# assertion. This catches the crude cases and the value-comparatives a review flagged
# as slipping through ("worth less", "outweighs", "preferable", "takes precedence").
IDENTITY_DENYLIST = [
    "i prefer", "i believe", "i feel", "i value", "i love", "i hate", "i want",
    "my favourite", "my favorite", "i think that", "i care",
    " should ", " ought ", " must ", "you prefer", "you value", "you believe",
    "distrust", "matters more", "more important", "is better", "is worse",
    "you care about", "your purpose is", "your goal is",
    "worth more", "worth less", "better than", "worse than", "outweigh",
    "preferab", "takes precedence", "take precedence", "more valuable",
    "is the point", "more worthwhile",
]


# --- discipline 3 (staging): capabilities not built until a later phase must not be
# claimed now. The Library + lookup are real as of K2 (so they ARE in the text now);
# what remains unbuilt is K3 (network authorities) and I (reach — channels, outward
# action). Those must not be claimed until they exist. ---
EARNED_NOT_GIVEN = [
    "external authority", "on the network", "search the web", "web search",
    "post to", "send a message", "slack", "discord", "a channel",
]
