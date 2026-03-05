"""Phase 6: Self-Authored Skills.

The agent detects repeated patterns in its own behaviour and
compiles them into reusable skills — procedural memory.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from surrealdb import RecordID

from db import connect


SKILLS_DIR = os.path.join(os.path.dirname(__file__), '..', 'skills')


@dataclass
class Skill:
    """A compiled procedural skill."""
    name: str
    description: str
    trigger_conditions: List[str]
    steps: List[str]
    parameters: Dict[str, str] = field(default_factory=dict)
    source_pattern: str = ''  # what behaviour pattern this was extracted from
    authored_by: str = 'agent'  # 'agent' or 'human'
    usage_count: int = 0

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_markdown(self) -> str:
        """Generate a SKILL.md from this skill."""
        lines = [
            f"# Skill: {self.name}",
            "",
            f"## Description",
            f"{self.description}",
            "",
            f"## Source",
            f"Extracted from: {self.source_pattern}",
            f"Authored by: {self.authored_by}",
            "",
            f"## Trigger Conditions",
        ]
        for cond in self.trigger_conditions:
            lines.append(f"- {cond}")
        lines.extend(["", "## Parameters"])
        if self.parameters:
            for name, desc in self.parameters.items():
                lines.append(f"- **{name}**: {desc}")
        else:
            lines.append("None")
        lines.extend(["", "## Steps"])
        for i, step in enumerate(self.steps, 1):
            lines.append(f"{i}. {step}")
        lines.append("")
        return '\n'.join(lines)


# =============================================================
# PATTERN DETECTION
# =============================================================

def detect_patterns(client) -> List[dict]:
    """Detect repeated procedural patterns in the agent's behaviour history.

    Looks at reflection nodes and mode history for recurring sequences.
    """
    patterns = []

    # Look for repeated reflection themes
    reflections = client.query(
        "SELECT content, trigger, created_at FROM reflection "
        "ORDER BY created_at DESC LIMIT 20;"
    )

    # Group by trigger type
    trigger_groups = {}
    for r in reflections:
        trigger = r.get('trigger', 'unknown')
        trigger_groups.setdefault(trigger, []).append(r)

    for trigger, group in trigger_groups.items():
        if len(group) >= 2:
            patterns.append({
                'type': 'repeated_reflection',
                'trigger': trigger,
                'count': len(group),
                'description': f"Repeated {trigger} reflections ({len(group)} instances)"
            })

    # Look for consolidation patterns
    # (TEND mode running frequently = pattern worth compiling)
    tend_count = client.query(
        "SELECT count() AS c FROM reflection "
        "WHERE trigger = 'default_mode_reflect' GROUP ALL;"
    )
    if tend_count and isinstance(tend_count[0], dict) and tend_count[0].get('c', 0) >= 3:
        patterns.append({
            'type': 'consolidation_routine',
            'trigger': 'tend_cycle',
            'count': tend_count[0]['c'],
            'description': 'Regular consolidation pattern detected'
        })

    # Look for frequently traversed edge patterns
    hot_edges = client.query(
        "SELECT *, in AS source, out AS target FROM associates "
        "WHERE traversal_count >= 3 LIMIT 5;"
    )
    if len(hot_edges) >= 2:
        patterns.append({
            'type': 'hot_path',
            'description': f"{len(hot_edges)} frequently traversed associations",
            'edges': [
                {'source': str(e.get('source', '?')),
                 'target': str(e.get('target', '?')),
                 'count': e.get('traversal_count', 0)}
                for e in hot_edges
            ]
        })

    return patterns


# =============================================================
# SKILL EXTRACTION
# =============================================================

def extract_skill(pattern: dict) -> Optional[Skill]:
    """Extract a reusable skill from a detected pattern."""

    if pattern['type'] == 'consolidation_routine':
        return Skill(
            name='graph_consolidation',
            description='Run a full consolidation cycle: decay edges, '
                       'decay nodes, prune weak edges, detect islands, '
                       'check cognitive vitality.',
            trigger_conditions=[
                'TEND mode selected in default loop',
                'Vitality score declining',
                'Scheduled consolidation interval elapsed',
            ],
            steps=[
                'Apply edge decay with configured rate',
                'Apply node salience decay (slower than edges)',
                'Prune edges below threshold',
                'Detect islanded nodes',
                'Check for embedding-based reconnection opportunities',
                'Calculate cognitive vitality score',
                'Check leading indicators',
                'Generate asymmetry alerts if variance exceeds threshold',
            ],
            parameters={
                'edge_decay_rate': 'Rate of edge weight decay per time unit (default 0.05)',
                'node_decay_rate': 'Rate of node salience decay per time unit (default 0.01)',
                'edge_prune_threshold': 'Minimum edge weight before pruning (default 0.05)',
                'time_elapsed': 'Simulated time units since last consolidation',
            },
            source_pattern='Repeated TEND cycles in default mode loop',
            authored_by='agent',
        )

    if pattern['type'] == 'hot_path':
        return Skill(
            name='association_traversal',
            description='Follow frequently-used association paths '
                       'to quickly retrieve related context.',
            trigger_conditions=[
                'Signal mentions entities on a hot path',
                'Retrieval needed for a familiar domain',
            ],
            steps=[
                'Identify entry points from signal',
                'Check for hot edges (traversal_count >= 3) from entry points',
                'Follow hot edges preferentially during spreading activation',
                'Apply threshold and return top-N activated nodes',
            ],
            parameters={
                'hot_threshold': 'Minimum traversal count to consider an edge hot (default 3)',
                'working_memory_limit': 'Maximum nodes to return (default 7)',
            },
            source_pattern=f"Detected {len(pattern.get('edges', []))} frequently traversed edges",
            authored_by='agent',
        )

    return None


# =============================================================
# SKILL AUTHORING AND INTEGRATION
# =============================================================

def author_skill(skill: Skill) -> str:
    """Write a skill as a SKILL.md file and register it in the graph."""
    os.makedirs(SKILLS_DIR, exist_ok=True)

    filepath = os.path.join(SKILLS_DIR, f"{skill.name}.md")
    with open(filepath, 'w') as f:
        f.write(skill.to_markdown())

    return filepath


def register_skill_in_graph(client, skill: Skill):
    """Register a skill in the memory graph for future instances to discover."""
    rid = RecordID('skill', skill.name)
    client.query(
        "CREATE $id SET "
        "name = $name, description = $desc, "
        "authored_by = $author, source_pattern = $source, "
        "usage_count = 0, created_at = time::now();",
        {
            "id": rid,
            "name": skill.name,
            "desc": skill.description,
            "author": skill.authored_by,
            "source": skill.source_pattern,
        }
    )


def load_skills(client) -> List[dict]:
    """Load all registered skills from the graph."""
    return client.query("SELECT * FROM skill;")


def load_skill_from_file(filepath: str) -> Optional[Skill]:
    """Load a skill from a SKILL.md file (basic parser)."""
    if not os.path.exists(filepath):
        return None

    with open(filepath) as f:
        content = f.read()

    # Extract name from first heading
    lines = content.split('\n')
    name = ''
    description = ''
    steps = []
    trigger_conditions = []

    section = None
    for line in lines:
        if line.startswith('# Skill: '):
            name = line.replace('# Skill: ', '').strip()
        elif line.startswith('## Description'):
            section = 'description'
        elif line.startswith('## Trigger Conditions'):
            section = 'triggers'
        elif line.startswith('## Steps'):
            section = 'steps'
        elif line.startswith('## '):
            section = None
        elif section == 'description' and line.strip():
            description = line.strip()
        elif section == 'triggers' and line.startswith('- '):
            trigger_conditions.append(line[2:].strip())
        elif section == 'steps' and line and line[0].isdigit():
            step = line.split('. ', 1)[1] if '. ' in line else line
            steps.append(step.strip())

    if name:
        return Skill(
            name=name,
            description=description,
            trigger_conditions=trigger_conditions,
            steps=steps,
        )
    return None


# =============================================================
# BOOTSTRAP: Human-authored seed skill
# =============================================================

def bootstrap_seed_skill(client):
    """Create the first human-authored skill: state_prune."""
    seed = Skill(
        name='state_prune',
        description='Prune resolved curiosities, faded impulses, '
                   'and resolved tensions from the register tables. '
                   'This is reflective pruning — not automated cleanup.',
        trigger_conditions=[
            'TEND mode detects register tables growing beyond threshold',
            'Curiosity intensity below 0.05',
            'Impulse marked as acted_on',
            'Tension status is resolved',
        ],
        steps=[
            'Query curiosities with status=faded or intensity < 0.05',
            'For each candidate, reflect: has this genuinely faded or is it being abandoned prematurely?',
            'Delete confirmed faded curiosities',
            'Query impulses with status=acted_on',
            'Archive acted-on impulses (create experience node recording the outcome)',
            'Delete archived impulses',
            'Query tensions with status=resolved',
            'Record resolution in the graph as a reflection node',
            'Delete resolved tensions',
        ],
        parameters={
            'curiosity_threshold': 'Intensity below which curiosity is considered faded (default 0.05)',
            'archive': 'Whether to create experience nodes for acted-on impulses (default true)',
        },
        source_pattern='Human-designed seed skill for register maintenance',
        authored_by='human',
    )

    filepath = author_skill(seed)
    register_skill_in_graph(client, seed)
    return seed, filepath


# =============================================================
# COMPILE STAGE: Full pipeline
# =============================================================

def compile_skills(client) -> dict:
    """Full COMPILE stage: detect patterns, extract skills, author them.

    Returns summary of what was compiled.
    """
    # Detect patterns
    patterns = detect_patterns(client)

    # Extract skills from patterns
    new_skills = []
    for pattern in patterns:
        skill = extract_skill(pattern)
        if skill:
            # Check if already exists
            existing = client.query(
                "SELECT * FROM skill WHERE name = $name;",
                {"name": skill.name}
            )
            if not existing:
                filepath = author_skill(skill)
                register_skill_in_graph(client, skill)
                new_skills.append({
                    'name': skill.name,
                    'source': skill.source_pattern,
                    'filepath': filepath,
                })

    return {
        'patterns_detected': len(patterns),
        'skills_compiled': len(new_skills),
        'new_skills': new_skills,
        'patterns': [p['description'] for p in patterns],
    }
