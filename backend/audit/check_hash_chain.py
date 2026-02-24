"""Vérifie l'intégrité de la chaîne d'audit (hash chain)."""

import asyncio
import sys

from app.db import get_engine, init_db, verify_hash_chain


async def check() -> dict:
    engine = get_engine()
    await init_db(engine)

    result = await verify_hash_chain(engine)

    violations = []
    if not result["ok"]:
        violations.append(f"Chaîne brisée à l'entrée #{result['broken_id']}")

    return {
        "check": "hash_chain_integrity",
        "chain_length": result["length"],
        "violations": violations,
        "passed": result["ok"],
    }


if __name__ == "__main__":
    result = asyncio.run(check())
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"{status} – Hash chain : {result['chain_length']} entrée(s), {len(result['violations'])} violation(s)")
    for v in result["violations"]:
        print(f"  ⚠️  {v}")
    sys.exit(0 if result["passed"] else 1)
