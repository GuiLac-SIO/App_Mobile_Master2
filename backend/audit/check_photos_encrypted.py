"""Vérifie que les photos sont stockées chiffrées (nonce, tag, key_id présents)."""

import asyncio
import sys

from app.db import get_engine, init_db, photos_table
from sqlalchemy import select


async def check() -> dict:
    engine = get_engine()
    await init_db(engine)

    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                select(
                    photos_table.c.id,
                    photos_table.c.object_name,
                    photos_table.c.nonce,
                    photos_table.c.tag,
                    photos_table.c.alg,
                    photos_table.c.key_id,
                )
            )
        ).mappings().all()

    violations = []
    for row in rows:
        reasons = []
        if not row["nonce"]:
            reasons.append("nonce manquant")
        if not row["tag"]:
            reasons.append("tag manquant")
        if not row["key_id"]:
            reasons.append("key_id manquant")
        if row["alg"] not in ("AES-256-GCM", "AES-128-GCM"):
            reasons.append(f"algorithme inconnu: {row['alg']}")
        if reasons:
            violations.append({"photo_id": row["id"], "object_name": row["object_name"], "reasons": reasons})

    return {
        "check": "photos_encrypted",
        "total_photos": len(rows),
        "violations": violations,
        "passed": len(violations) == 0,
    }


if __name__ == "__main__":
    result = asyncio.run(check())
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    print(f"{status} – Photos chiffrées : {result['total_photos']} photos, {len(result['violations'])} violation(s)")
    for v in result["violations"]:
        print(f"  ⚠️  photo #{v['photo_id']} ({v['object_name']}): {', '.join(v['reasons'])}")
    sys.exit(0 if result["passed"] else 1)
