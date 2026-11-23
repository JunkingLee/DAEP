#!/usr/bin/env python3
"""Assert security-critical properties of the rendered production Compose model."""
import json
import subprocess
import sys


def fail(message: str) -> None:
    raise SystemExit(f"production compose security check failed: {message}")


compose_file = sys.argv[1] if len(sys.argv) > 1 else "compose.production.yaml"
result = subprocess.run(
    ["docker", "compose", "--profile", "broker", "-f", compose_file, "config", "--format", "json"],
    check=True,
    capture_output=True,
    text=True,
)
model = json.loads(result.stdout)
services = model.get("services", {})

for required in ("postgres", "migrate", "daep-api", "daep-worker"):
    if required not in services:
        fail(f"missing service {required}")

postgres = services["postgres"]
if postgres.get("ports"):
    fail("PostgreSQL must not publish host ports")

api = services["daep-api"]
environment = api.get("environment", {})
runtime_url = str(environment.get("DATABASE_URL", ""))
privileged_url = str(environment.get("DAEP_PRIVILEGED_DATABASE_URL", ""))
if "daep_runtime:" not in runtime_url:
    fail("API DATABASE_URL must use daep_runtime")
if "daep_privileged_login:" not in privileged_url:
    fail("API privileged URL must use daep_privileged_login")
if "daep_bootstrap" in runtime_url or "daep_bootstrap" in privileged_url:
    fail("API must never receive bootstrap database credentials")
if api.get("read_only") is not True:
    fail("API filesystem must be read-only")
if "ALL" not in api.get("cap_drop", []):
    fail("API must drop all Linux capabilities")
if "no-new-privileges:true" not in api.get("security_opt", []):
    fail("API must enable no-new-privileges")
if "/tmp" not in api.get("tmpfs", []):
    fail("API must mount /tmp as tmpfs")

depends = api.get("depends_on", {}).get("migrate", {})
if depends.get("condition") != "service_completed_successfully":
    fail("API must wait for successful one-shot migrations")

ports = api.get("ports", [])
if not ports:
    fail("API must declare its explicitly bound host port")
for port in ports:
    if port.get("host_ip") != "127.0.0.1":
        fail("API must bind to loopback by default")

worker = services["daep-worker"]
if "broker" not in worker.get("profiles", []):
    fail("worker must remain opt-in behind the broker profile")

print("production Compose security assertions passed")
