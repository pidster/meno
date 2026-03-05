"""Phase 5: Multi-Instance and Sensorium.

Multiple agent instances sharing a graph, focus modes,
task suspension/reconstruction, and sensorium channels.
Instances coordinate through the shared graph, not directly.
"""

import json
import os
import subprocess
import time as time_mod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from surrealdb import RecordID

from db import connect
from retrieval import (
    identify_entry_points, spread_activation, apply_threshold,
    RetrievalConfig, RetrievalResult
)


# =============================================================
# FOCUS MODES
# =============================================================

FOCUS_MODES = {
    'DEEP_FOCUS': {
        'interrupt_threshold': 0.95,  # only critical interrupts
        'description': 'Flow state — queue all but critical interrupts'
    },
    'ACTIVE_ENGAGED': {
        'interrupt_threshold': 0.7,
        'description': 'Normal work — accept high-salience interrupts'
    },
    'RESPONSIVE': {
        'interrupt_threshold': 0.3,
        'description': 'Conversation — accept all above-threshold'
    },
    'WINDING_DOWN': {
        'interrupt_threshold': 0.5,
        'description': 'Completing current sub-task then transitioning'
    },
}


# =============================================================
# INSTANCE MANAGEMENT
# =============================================================

@dataclass
class Instance:
    """Represents an agent instance operating on the shared graph."""
    instance_id: str
    instance_type: str  # 'default_mode', 'engaged', 'supervisory'
    focus_mode: str = 'ACTIVE_ENGAGED'
    current_task: Optional[str] = None
    interrupt_queue: List[dict] = field(default_factory=list)
    active: bool = True

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def register_instance(client, instance: Instance):
    """Register an instance in the shared graph."""
    client.query(
        "CREATE type::record('instance', $id) SET "
        "instance_type = $type, focus_mode = $mode, "
        "current_task = $task, active = $active, "
        "registered_at = time::now();",
        {
            "id": instance.instance_id,
            "type": instance.instance_type,
            "mode": instance.focus_mode,
            "task": instance.current_task,
            "active": instance.active,
        }
    )


def update_instance(client, instance: Instance):
    """Update instance state in the graph."""
    client.query(
        "UPDATE type::record('instance', $id) SET "
        "focus_mode = $mode, current_task = $task, "
        "active = $active, updated_at = time::now();",
        {
            "id": instance.instance_id,
            "mode": instance.focus_mode,
            "task": instance.current_task,
            "active": instance.active,
        }
    )


def get_active_instances(client) -> list:
    """Get all active instances from the graph."""
    return client.query("SELECT * FROM instance WHERE active = true;")


def set_focus_mode(client, instance: Instance, mode: str):
    """Change an instance's focus mode."""
    assert mode in FOCUS_MODES, f"Unknown focus mode: {mode}"
    instance.focus_mode = mode
    update_instance(client, instance)


# =============================================================
# TASK SUSPENSION AND RECONSTRUCTION
# =============================================================

def suspend_task(client, instance: Instance, reason: str = 'manual') -> str:
    """Suspend current task, saving state to the graph.

    Returns the suspended task node ID.
    """
    if not instance.current_task:
        return None

    task_id = f"suspended_{instance.current_task}_{int(time_mod.time())}"

    client.query(
        "CREATE type::record('suspended_task', $id) SET "
        "task_name = $task, instance_id = $iid, "
        "reason = $reason, suspended_at = time::now(), "
        "status = 'suspended';",
        {
            "id": task_id,
            "task": instance.current_task,
            "iid": instance.instance_id,
            "reason": reason,
        }
    )

    # Create edges to entities relevant to the task
    # Use the task name as a signal to find related nodes
    signal = {'keywords': [instance.current_task]}
    entry_points = identify_entry_points(client, signal)
    task_rid = RecordID('suspended_task', task_id)
    for node_id, activation in entry_points.items():
        parts = node_id.split(":", 1)
        node_rid = RecordID(parts[0], parts[1])
        client.query(
            "RELATE $task->associates->$node SET "
            "weight = $w, edge_type = 'was_working_on', "
            "created_at = time::now(), traversal_count = 0;",
            {"task": task_rid, "node": node_rid, "w": activation}
        )

    instance.current_task = None
    update_instance(client, instance)

    return task_id


def reconstruct_task(client, task_id: str) -> RetrievalResult:
    """Reconstruct a suspended task's context via spreading activation.

    This is NOT snapshot loading — it rebuilds context through the graph,
    incorporating any new connections made since suspension.
    """
    task_rid = RecordID('suspended_task', task_id)
    task_node = client.query("SELECT * FROM $node;", {"node": task_rid})
    if not task_node:
        return None

    # Use the task node as an entry point for spreading activation
    config = RetrievalConfig(
        decay_per_hop=0.6,
        max_hops=3,
        min_transmission=0.01,
        activation_threshold=0.05,
        working_memory_limit=10
    )

    # Start activation from the task node and its edges
    entry_points = {f"suspended_task:{task_id}": 1.0}

    # Also activate from nodes the task was connected to
    edges = client.query(
        "SELECT out AS target FROM associates WHERE in = $node;",
        {"node": task_rid}
    )
    for edge in edges:
        target_id = str(edge['target'])
        entry_points[target_id] = 0.8

    result = spread_activation(client, entry_points, config)
    result = apply_threshold(result, config)

    # Mark task as reconstructed
    client.query(
        "UPDATE $node SET status = 'reconstructed', "
        "reconstructed_at = time::now();",
        {"node": task_rid}
    )

    return result


# =============================================================
# SENSORIUM CHANNELS
# =============================================================

@dataclass
class SensoriumEvent:
    """An event from a sensorium channel."""
    channel: str
    event_type: str
    content: str
    salience: float
    metadata: dict = field(default_factory=dict)


def sense_filesystem(project_dir: str) -> List[SensoriumEvent]:
    """Filesystem sensorium channel: detect file changes."""
    events = []
    for root, dirs, files in os.walk(project_dir):
        # Skip hidden dirs and common noise
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in files:
            if fname.startswith('.'):
                continue
            fpath = os.path.join(root, fname)
            try:
                mtime = os.path.getmtime(fpath)
                events.append(SensoriumEvent(
                    channel='filesystem',
                    event_type='file_present',
                    content=os.path.relpath(fpath, project_dir),
                    salience=0.1,  # low base salience
                    metadata={'modified': mtime, 'size': os.path.getsize(fpath)}
                ))
            except OSError:
                pass
    return events


def sense_git(repo_dir: str) -> List[SensoriumEvent]:
    """Git repository sensorium channel: detect recent commits and status."""
    events = []

    try:
        # Recent commits
        result = subprocess.run(
            ['git', 'log', '--oneline', '-5', '--format=%H|%s|%an|%ar'],
            cwd=repo_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue
                parts = line.split('|', 3)
                if len(parts) >= 2:
                    events.append(SensoriumEvent(
                        channel='git',
                        event_type='commit',
                        content=parts[1] if len(parts) > 1 else parts[0],
                        salience=0.5,
                        metadata={
                            'hash': parts[0][:8],
                            'author': parts[2] if len(parts) > 2 else 'unknown',
                            'age': parts[3] if len(parts) > 3 else 'unknown'
                        }
                    ))

        # Working tree status
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            cwd=repo_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0 and result.stdout.strip():
            changed_files = result.stdout.strip().split('\n')
            events.append(SensoriumEvent(
                channel='git',
                event_type='uncommitted_changes',
                content=f"{len(changed_files)} uncommitted changes",
                salience=0.4,
                metadata={'files': changed_files[:10]}
            ))

        # Current branch
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            cwd=repo_dir, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            events.append(SensoriumEvent(
                channel='git',
                event_type='branch',
                content=f"On branch: {branch}",
                salience=0.2,
                metadata={'branch': branch}
            ))

    except (subprocess.TimeoutExpired, FileNotFoundError):
        events.append(SensoriumEvent(
            channel='git',
            event_type='error',
            content='Git channel unavailable',
            salience=0.1,
            metadata={}
        ))

    return events


# =============================================================
# SUPERVISORY INSTANCE
# =============================================================

SALIENCE_THRESHOLDS = {
    'discard': 0.2,
    'encode': 0.4,
    'interrupt': 0.7,
}


def compute_event_salience(event: SensoriumEvent, client) -> float:
    """Compute salience of a sensorium event against the graph."""
    base = event.salience

    # Boost if event mentions a known entity
    signal = {'keywords': event.content.split()[:5]}
    entry_points = identify_entry_points(client, signal)
    if entry_points:
        base += 0.2 * len(entry_points)

    # Boost for novel event types
    if event.event_type in ('commit', 'uncommitted_changes'):
        base += 0.1

    return min(1.0, base)


def supervisory_poll(client, project_dir: str) -> dict:
    """Run one supervisory polling cycle across all sensorium channels.

    Returns summary of events detected and actions taken.
    """
    all_events = []

    # Poll filesystem
    fs_events = sense_filesystem(project_dir)
    all_events.extend(fs_events)

    # Poll git
    git_events = sense_git(project_dir)
    all_events.extend(git_events)

    # Process events through salience gate
    discarded = 0
    encoded = 0
    interrupts = []

    for event in all_events:
        salience = compute_event_salience(event, client)

        if salience < SALIENCE_THRESHOLDS['discard']:
            discarded += 1
            continue

        if salience < SALIENCE_THRESHOLDS['interrupt']:
            # Encode but don't interrupt
            encoded += 1
            continue

        # High salience — potential interrupt
        interrupts.append({
            'channel': event.channel,
            'type': event.event_type,
            'content': event.content,
            'salience': salience,
        })

    # Route interrupts to active instances
    active = get_active_instances(client)
    routed = []
    for interrupt in interrupts:
        for inst in active:
            mode = inst.get('focus_mode', 'RESPONSIVE')
            threshold = FOCUS_MODES.get(mode, {}).get('interrupt_threshold', 0.5)
            if interrupt['salience'] >= threshold:
                routed.append({
                    'interrupt': interrupt,
                    'target_instance': str(inst.get('id', 'unknown'))
                })
                break

    return {
        'total_events': len(all_events),
        'discarded': discarded,
        'encoded': encoded,
        'interrupts': len(interrupts),
        'routed': len(routed),
        'channels': {
            'filesystem': len(fs_events),
            'git': len(git_events),
        }
    }
