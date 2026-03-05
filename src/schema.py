"""Phase 1: Memory Graph Schema — defines all node types, edge types,
and register tables in SurrealDB."""

SCHEMA_DDL = """
-- =============================================================
-- NODE TYPES
-- =============================================================

-- An experience: a discrete unit of something that happened.
-- Stores cues for reconstruction, not complete records.
DEFINE TABLE experience SCHEMAFULL;
  DEFINE FIELD content          ON experience TYPE string;
  DEFINE FIELD summary          ON experience TYPE string;
  DEFINE FIELD context          ON experience TYPE object FLEXIBLE;
  DEFINE FIELD salience         ON experience TYPE float;
  DEFINE FIELD created_at       ON experience TYPE datetime;
  DEFINE FIELD last_activated   ON experience TYPE option<datetime>;
  DEFINE FIELD activation_count ON experience TYPE int DEFAULT 0;
  DEFINE FIELD tags             ON experience TYPE array<string>;
  DEFINE FIELD embedding        ON experience TYPE option<array<float>>;

-- A concept: an abstraction emerging from multiple experiences.
DEFINE TABLE concept SCHEMAFULL;
  DEFINE FIELD name             ON concept TYPE string;
  DEFINE FIELD description      ON concept TYPE string;
  DEFINE FIELD salience         ON concept TYPE float;
  DEFINE FIELD last_activated   ON concept TYPE option<datetime>;
  DEFINE FIELD activation_count ON concept TYPE int DEFAULT 0;
  DEFINE FIELD embedding        ON concept TYPE option<array<float>>;

-- An entity: a person, project, tool, or thing persisting across experiences.
DEFINE TABLE entity SCHEMAFULL;
  DEFINE FIELD name             ON entity TYPE string;
  DEFINE FIELD entity_type      ON entity TYPE string;
  DEFINE FIELD properties       ON entity TYPE object FLEXIBLE;
  DEFINE FIELD salience         ON entity TYPE float;
  DEFINE FIELD last_activated   ON entity TYPE option<datetime>;

-- A reflection: the agent's own meta-cognitive observations.
DEFINE TABLE reflection SCHEMAFULL;
  DEFINE FIELD content          ON reflection TYPE string;
  DEFINE FIELD trigger          ON reflection TYPE string;
  DEFINE FIELD created_at       ON reflection TYPE datetime;
  DEFINE FIELD salience         ON reflection TYPE float;
  DEFINE FIELD embedding        ON reflection TYPE option<array<float>>;

-- =============================================================
-- EDGE TYPES
-- =============================================================

-- Associative link: the fundamental weighted connection.
DEFINE TABLE associates SCHEMAFULL TYPE RELATION;
  DEFINE FIELD weight           ON associates TYPE float;
  DEFINE FIELD edge_type        ON associates TYPE string;
  DEFINE FIELD created_at       ON associates TYPE datetime;
  DEFINE FIELD last_traversed   ON associates TYPE option<datetime>;
  DEFINE FIELD traversal_count  ON associates TYPE int DEFAULT 0;

-- Participation: links entities to experiences.
DEFINE TABLE participated_in SCHEMAFULL TYPE RELATION;
  DEFINE FIELD role             ON participated_in TYPE string;

-- Instantiation: links experiences to concepts they exemplify.
DEFINE TABLE exemplifies SCHEMAFULL TYPE RELATION;
  DEFINE FIELD strength         ON exemplifies TYPE float;

-- Temporal ordering between experiences.
DEFINE TABLE followed_by SCHEMAFULL TYPE RELATION;
  DEFINE FIELD gap_seconds      ON followed_by TYPE int;

-- =============================================================
-- REGISTER TABLES (Revision Note #1)
-- Curiosities, tensions, and impulses have distinct dynamics.
-- =============================================================

-- Curiosity: about external information gaps. Decays when unattended.
DEFINE TABLE curiosity SCHEMAFULL;
  DEFINE FIELD description      ON curiosity TYPE string;
  DEFINE FIELD intensity        ON curiosity TYPE float;
  DEFINE FIELD status           ON curiosity TYPE string DEFAULT 'active';
  DEFINE FIELD created_at       ON curiosity TYPE datetime;
  DEFINE FIELD last_checked     ON curiosity TYPE option<datetime>;
  DEFINE FIELD decay_rate       ON curiosity TYPE float DEFAULT 0.1;
  DEFINE FIELD source_node      ON curiosity TYPE option<record>;

-- Impulse: about internal cognitive incompletion. Builds pressure.
DEFINE TABLE impulse SCHEMAFULL;
  DEFINE FIELD description      ON impulse TYPE string;
  DEFINE FIELD intensity        ON impulse TYPE float;
  DEFINE FIELD status           ON impulse TYPE string DEFAULT 'deferred';
  DEFINE FIELD created_at       ON impulse TYPE datetime;
  DEFINE FIELD deferred_count   ON impulse TYPE int DEFAULT 0;
  DEFINE FIELD pressure_rate    ON impulse TYPE float DEFAULT 0.15;
  DEFINE FIELD source_node      ON impulse TYPE option<record>;

-- Tension: unresolved contradictions or conflicts in the graph.
DEFINE TABLE tension SCHEMAFULL;
  DEFINE FIELD description      ON tension TYPE string;
  DEFINE FIELD intensity        ON tension TYPE float;
  DEFINE FIELD status           ON tension TYPE string DEFAULT 'unresolved';
  DEFINE FIELD created_at       ON tension TYPE datetime;
  DEFINE FIELD node_a           ON tension TYPE option<record>;
  DEFINE FIELD node_b           ON tension TYPE option<record>;

-- =============================================================
-- INSTANCE AND TASK TABLES (Phase 5)
-- =============================================================

-- Agent instance: represents a running instance sharing the graph.
DEFINE TABLE instance SCHEMALESS;

-- Suspended task: state saved to graph for later reconstruction.
DEFINE TABLE suspended_task SCHEMALESS;
"""


def apply_schema(client):
    """Apply the full schema DDL to the connected SurrealDB instance."""
    result = client.query(SCHEMA_DDL)
    return result
