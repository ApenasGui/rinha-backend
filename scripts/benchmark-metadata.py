#!/usr/bin/env python3
"""Capture public machine/runtime facts and hashes; never dump environment values."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def command(arguments):
    result = subprocess.run(arguments, cwd=ROOT, capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else {"exit_code": result.returncode, "stderr": result.stderr.strip()}


def file_hashes():
    files = [*ROOT.glob("src/**/*.ts"), *ROOT.glob("infra/*"), *ROOT.glob("docker-compose*.yml"), *(ROOT / name for name in ("Dockerfile", "package.json", "package-lock.json", "benchmark/official-source.json"))]
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files if path.is_file()}


def main():
    run, label = Path(sys.argv[1]), sys.argv[2]
    if label == "--verify":
        before = json.loads((run / "environment.json").read_text())["file_sha256"]
        after = file_hashes()
        changed = sorted(name for name in before.keys() | after.keys() if before.get(name) != after.get(name))
        integrity = {"unchanged": not changed, "changed_files": changed, "file_sha256_after": after}
        (run / "source-integrity.json").write_text(json.dumps(integrity, ensure_ascii=False, indent=2) + "\n")
        if changed:
            print("Application files changed during the run: " + ", ".join(changed), file=sys.stderr)
            sys.exit(1)
        return
    config = json.loads(command(["docker", "compose", "config", "--format", "json"]))
    services = {}
    for name, service in config["services"].items():
        environment = service.get("environment", {})
        services[name] = {
            "image": service.get("image"),
            "network_mode": service.get("network_mode", "Compose bridge network"),
            "limits": service.get("deploy", {}).get("resources", {}).get("limits"),
            "settings": {key: environment[key] for key in ("NODE_ENV", "SEARCH_MODE", "CACHE_SIZE", "DB_POOL_SIZE") if key in environment},
        }
    hashes = file_hashes()
    limits = {}
    for filename in ("cpu.max", "memory.max", "cpuset.cpus.effective", "cpu.stat"):
        path = Path("/sys/fs/cgroup") / filename
        if path.is_file():
            limits[filename] = path.read_text().strip()
    containers = command(["docker", "compose", "ps", "-q"]).split()
    runtime_images = []
    if containers:
        template = '{"name":{{json .Name}},"image":{{json .Image}}}'
        for line in command(["docker", "inspect", "--format", template, *containers]).splitlines():
            container = json.loads(line)
            image = json.loads(command(["docker", "image", "inspect", container["image"]]))[0]
            runtime_images.append({
                "container": container["name"].lstrip("/"),
                "image_id": image["Id"],
                "repo_digests": image.get("RepoDigests", []),
                "architecture": image["Architecture"],
                "os": image["Os"],
            })
    docker_info = json.loads(command(["docker", "info", "--format", "{{json .}}"] ))
    output = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "platform": platform.platform(),
        "kernel": platform.release(),
        "logical_cpus_visible": os.cpu_count(),
        "cpu_affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "task_cgroup": limits,
        "lscpu": json.loads(command(["lscpu", "--json"])),
        "memory": command(["free", "--bytes"]),
        "docker_version": command(["docker", "version", "--format", "{{json .}}"]),
        "compose_version": command(["docker", "compose", "version", "--short"]),
        "compose_files": os.environ.get("COMPOSE_FILE", str(ROOT / "docker-compose.yml")),
        "docker_host": {key: docker_info.get(key) for key in ("Driver", "NCPU", "MemTotal", "CgroupDriver", "CgroupVersion", "KernelVersion", "OperatingSystem", "DockerRootDir")},
        "runtime_images": runtime_images,
        "git_commit": command(["git", "rev-parse", "HEAD"]),
        "working_tree": command(["git", "status", "--short"]),
        "file_sha256": hashes,
        "services": services,
        "generator_jvm_options": "-Xms256m -Xmx1g -XX:ActiveProcessorCount=2",
        "generator_location": "same cloud machine, outside the application containers and their resource budget",
        "official_injection_seconds": 205,
        "initial_person_count": 0,
    }
    (run / "environment.json").write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
