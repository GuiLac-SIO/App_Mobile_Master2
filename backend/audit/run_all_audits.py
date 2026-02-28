"""Lance tous les audits de sécurité et produit un rapport consolidé."""

import asyncio
import json
import sys
from datetime import datetime, timezone

from audit.check_hash_chain import check as check_hash_chain
from audit.check_iam import check as check_iam
from audit.check_network import check as check_network
from audit.check_photos_encrypted import check as check_photos
from audit.check_votes_encrypted import check as check_votes


ASYNC_CHECKS = [
    check_votes,
    check_photos,
    check_iam,
    check_hash_chain,
]


async def run_async_checks() -> list[dict]:
    results = []
    for fn in ASYNC_CHECKS:
        results.append(await fn())
    return results


def main():
    print("=" * 60)
    print("  🔒 AUDIT DE SÉCURITÉ – Secure Votes System")
    print(f"  📅 {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 60)
    print()

    async_results = asyncio.run(run_async_checks())

    network_result = check_network()

    all_results = async_results + [network_result]

    passed = 0
    failed = 0
    for r in all_results:
        icon = "✅" if r["passed"] else "❌"
        name = r["check"]
        violations = r.get("violations", [])
        if r["passed"]:
            passed += 1
            print(f"  {icon} {name}")
        else:
            failed += 1
            print(f"  {icon} {name} ({len(violations)} violation(s))")
            for v in violations:
                if isinstance(v, dict):
                    print(f"      ⚠️  {json.dumps(v, ensure_ascii=False)}")
                else:
                    print(f"      ⚠️  {v}")

    print()
    print("-" * 60)
    total = passed + failed
    print(f"  Résultat : {passed}/{total} vérifications réussies")

    if failed:
        print(f"  ⚠️  {failed} vérification(s) en échec")
    else:
        print("  🎉 Tous les audits sont passés avec succès")

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": {"total": total, "passed": passed, "failed": failed},
        "checks": all_results,
    }
    report_path = "audit_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  📄 Rapport JSON exporté : {report_path}")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
