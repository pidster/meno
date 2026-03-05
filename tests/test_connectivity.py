"""Phase 0 validation: SurrealDB connectivity test."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from db import connect


def test_create_and_query():
    """Verify we can connect, create a record, and query it back."""
    client = connect()

    # Clean up any previous test data
    client.query("DELETE test_record;")

    # Create a record
    client.query("""
        CREATE test_record:hello SET
            name = 'meno',
            purpose = 'cognitive architecture',
            created = time::now()
        ;
    """)

    # Query it back
    result = client.query("SELECT * FROM test_record:hello;")

    # The result structure from surrealdb v2 client
    assert result is not None
    # Extract the record - result format varies by client version
    if isinstance(result, list):
        records = result[0] if result else []
    else:
        records = result

    if isinstance(records, dict):
        record = records
    elif isinstance(records, list) and len(records) > 0:
        record = records[0]
    else:
        raise AssertionError(f"Unexpected result format: {result}")

    assert record['name'] == 'meno'
    assert record['purpose'] == 'cognitive architecture'

    # Clean up
    client.query("DELETE test_record;")

    print("PASS: SurrealDB connectivity verified")
    print(f"  - Created record with name='{record['name']}'")
    print(f"  - Purpose: {record['purpose']}")
    return True


if __name__ == '__main__':
    try:
        test_create_and_query()
    except Exception as e:
        print(f"FAIL: {e}")
        sys.exit(1)
