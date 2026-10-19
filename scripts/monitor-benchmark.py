#!/usr/bin/env python3
"""Sample actual container resource use without including container environment."""
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import subprocess
import sys
import time

running = True


def stop(_signal, _frame):
    global running
    running = False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
with Path(sys.argv[1]).open("a", buffering=1) as stream:
    while running:
        result = subprocess.run(["docker", "compose", "ps", "-q"], capture_output=True, text=True)
        containers = result.stdout.split()
        if containers:
            result = subprocess.run(["docker", "stats", "--no-stream", "--format", "{{json .}}", *containers], capture_output=True, text=True)
            sample = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "containers": [json.loads(line) for line in result.stdout.splitlines() if line.startswith("{")]}
            stream.write(json.dumps(sample) + "\n")
        time.sleep(3)
