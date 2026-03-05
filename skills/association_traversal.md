# Skill: association_traversal

## Description
Follow frequently-used association paths to quickly retrieve related context.

## Source
Extracted from: Detected 5 frequently traversed edges
Authored by: agent

## Trigger Conditions
- Signal mentions entities on a hot path
- Retrieval needed for a familiar domain

## Parameters
- **hot_threshold**: Minimum traversal count to consider an edge hot (default 3)
- **working_memory_limit**: Maximum nodes to return (default 7)

## Steps
1. Identify entry points from signal
2. Check for hot edges (traversal_count >= 3) from entry points
3. Follow hot edges preferentially during spreading activation
4. Apply threshold and return top-N activated nodes
