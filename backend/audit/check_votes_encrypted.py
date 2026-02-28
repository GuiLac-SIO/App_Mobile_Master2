"""Vérifie que tous les votes stockés sont chiffrés (pas des valeurs binaires en clair)."""

import asyncio
import sys

from app.db import get_engine, init_db, votes_table
from sqlalchemy import select


async def check() -> dict:
    engine = get_engine()
    await init_db(engine)

    async with engine.connect() as conn:
        rows = (await conn.execute(select(votes_table.c.id, votes_table.c.ciphertext))).mappings().all()

    violations = []
    for row in rows:
        ct = row["ciphertext"].strip()
        if ct in ("0", "1", ""):
            violations.append({"vote_id": row["id"], "ciphertext": ct, "reason": "valeur binaire en clair"})
        elif len(ct) < 10:
            violations.append({"vote_id": row["id"], "ciphertext": ct, "reason": "ciphertext trop court pour Paillier"})

    return {
        "check": "votes_encrypted",
        "total_votes": len(rows),
        "violations": violations,
        "passed": len(violations) == 0,
    }


if __name__ == "__main__":
    result = asyncio.run(check())
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"{status} – Votes chiffrés : {result['total_votes']} votes, {len(result['violations'])} violation(s)")
    for v in result["violations"]:
        print(f"  ⚠️  vote #{v['vote_id']}: {v['reason']} (valeur={v['ciphertext']})")
    sys.exit(0 if result["passed"] else 1)
