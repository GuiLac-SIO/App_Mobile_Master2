"""Vérifie que seuls les ports attendus sont exposés par les conteneurs Docker."""

import json
import subprocess
import sys


EXPECTED_PORTS = {
    "api": {"8000/tcp"},
    "db": {"5432/tcp"},
    "minio": {"9000/tcp", "9001/tcp"},
    "frontend": {"80/tcp"},
}

ALLOWED_PROTOCOLS = {"tcp"}


def check() -> dict:
    try:
        raw = subprocess.check_output(
            ["docker", "compose", "ps", "--format", "json"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return {
            "check": "network_ports",
            "violations": ["Impossible d'exécuter 'docker compose ps'"],
            "passed": False,
        }

    violations = []
    services_checked = []

    for line in raw.strip().splitlines():
        try:
            container = json.loads(line)
        except json.JSONDecodeError:
            continue

        service = container.get("Service", container.get("Name", "unknown"))
        services_checked.append(service)

        publishers = container.get("Publishers") or []
        for pub in publishers:
            port_str = f"{pub.get('TargetPort')}/{pub.get('Protocol', 'tcp')}"
            protocol = pub.get("Protocol", "tcp")

            if protocol not in ALLOWED_PROTOCOLS:
                violations.append(f"{service}: protocole non sécurisé '{protocol}' sur port {pub.get('TargetPort')}")

            expected = EXPECTED_PORTS.get(service, set())
            if expected and port_str not in expected:
                violations.append(f"{service}: port inattendu exposé {port_str}")

    return {
        "check": "network_ports",
        "services_checked": services_checked,
        "violations": violations,
        "passed": len(violations) == 0,
    }


if __name__ == "__main__":
    result = check()
    status = "✅ PASS" if result["passed"] else "❌ FAIL"
    services = result.get("services_checked", [])
    print(f"{status} – Ports réseau : {len(services)} service(s), {len(result['violations'])} violation(s)")
    for v in result["violations"]:
        print(f"  ⚠️  {v}")
    sys.exit(0 if result["passed"] else 1)
