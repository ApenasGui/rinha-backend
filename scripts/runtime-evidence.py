#!/usr/bin/env python3
"""Capture resource failures and durable database state after the load drains."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent.parent


def command(*args):
    return subprocess.check_output(args, cwd=root, text=True).strip()


def counters(service, filename):
    return {line.split()[0]: int(line.split()[1]) for line in command(
        'docker', 'compose', 'exec', '-T', service, 'cat', f'/sys/fs/cgroup/{filename}'
    ).splitlines()}


evidence = {'captured_at_utc': datetime.now(timezone.utc).isoformat(), 'containers': {}}
for name in ['api1', 'api2', 'db', 'nginx']:
    identifier = command('docker', 'compose', 'ps', '-q', name)
    state = json.loads(command('docker', 'inspect', '--format', '{{json .State}}', identifier))
    evidence['containers'][name] = {
        'running': state['Running'], 'container_oom_killed': state['OOMKilled'],
        'memory_events': counters(name, 'memory.events'),
        'cpu_stat': counters(name, 'cpu.stat'),
    }
sql = "SELECT json_build_object('count', (SELECT count(*) FROM pessoas), 'fsync', current_setting('fsync'), 'synchronous_commit', current_setting('synchronous_commit'), 'full_page_writes', current_setting('full_page_writes'))"
evidence['database'] = json.loads(command('docker', 'compose', 'exec', '-T', 'db', 'psql', '-U', 'rinha', '-d', 'rinha', '-Atc', sql))
run = Path(sys.argv[1])
path = run / 'runtime-after.json'
if path.exists():
    raise SystemExit('Refusing to overwrite existing runtime evidence')
path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(evidence, ensure_ascii=False, indent=2))
