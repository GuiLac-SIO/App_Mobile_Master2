"""Vérifie les permissions IAM du rôle base de données (moindre privilège)."""

import asyncio
import sys

from app.db import get_engine, init_db, verify_db_permissions


async def check() -> dict:
    engine = get_engine()
    await init_db(engine)

    perms = await verify_db_permissions(engine)

    violations = []

    for attr in ("rolsuper", "rolcreatedb", "rolcreaterole", "rolreplication"):
        if perms.get(attr):
            violations.append(f"Le rôle a le privilège interdit : {attr}")

    required_grants = {
        "can_insert_votes": "INSERT sur votes.votes",
        "can_select_votes": "SELECT sur votes.votes",
        "can_select_identities": "SELECT sur identity.participants",
    }
    for key, desc in required_grants.items():
        if not perms.get(key):
            violations.append(f"Droit requis manquant : {desc}")

    return {
        "check": "iam_least_privilege",
        "permissions": perms,
        "violations": violations,
        "passed": len(violations) == 0,
    }


if __name__ == "__main__":
    result = asyncio.run(check())
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"{status} – IAM moindre privilège : {len(result['violations'])} violation(s)")
    for v in result["violations"]:
        print(f"  ⚠️  {v}")
    if result["passed"]:
        p = result["permissions"]
        print(f"  ℹ️  superuser={p['rolsuper']}, createdb={p['rolcreatedb']}, createrole={p['rolcreaterole']}")
    sys.exit(0 if result["passed"] else 1)
