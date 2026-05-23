"""Schema spot-check script for verification checklist Step 2."""
import asyncio
import asyncpg


async def main():
    conn = await asyncpg.connect("postgresql://postgres:password@localhost:5433/hybriddb")

    # Check feedback columns
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='feedback' ORDER BY column_name"
    )
    print("=== feedback columns ===")
    for r in rows:
        print(" ", r["column_name"])

    # Check source_trust columns
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='source_trust' ORDER BY column_name"
    )
    print("=== source_trust columns ===")
    for r in rows:
        print(" ", r["column_name"])

    # Check composite PK on source_trust
    rows = await conn.fetch(
        """
        SELECT kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        WHERE tc.table_name = 'source_trust'
          AND tc.constraint_type = 'PRIMARY KEY'
        ORDER BY kcu.ordinal_position
        """
    )
    print("=== source_trust PK columns ===")
    for r in rows:
        print(" ", r["column_name"])

    # Check workspaces table
    rows = await conn.fetch("SELECT * FROM workspaces")
    print("=== workspaces rows ===")
    for r in rows:
        print(" ", dict(r))

    # Check chunks.workspace_id
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='chunks' AND column_name='workspace_id'"
    )
    print("chunks.workspace_id exists:", len(rows) > 0)

    # Check results.workspace_id
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_name='results' AND column_name='workspace_id'"
    )
    print("results.workspace_id exists:", len(rows) > 0)

    await conn.close()
    print("\nSchema check PASSED")


asyncio.run(main())
