import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';

const compose = (...args) => execFileSync('docker', ['compose', ...args], { encoding: 'utf8' }).trim();
const names = ['api1', 'api2', 'db', 'nginx'];
const config = JSON.parse(compose('config', '--format', 'json'));
assert.deepEqual(Object.keys(config.services).sort(), [...names].sort(), 'Verifique todos os serviços no orçamento');

let nanoCpus = 0;
let memoryBytes = 0;
const limits = {};
for (const name of names) {
  const id = compose('ps', '-q', name);
  assert.ok(id, `${name} precisa estar em execução`);
  const [container] = JSON.parse(execFileSync('docker', ['inspect', id], { encoding: 'utf8' }));
  assert.equal(container.State.Running, true, `${name} não está em execução`);
  assert.equal(container.State.OOMKilled, false, `${name} sofreu OOM`);
  const cpu = container.HostConfig.NanoCpus;
  const memory = container.HostConfig.Memory;
  assert.ok(cpu > 0 && memory > 0, `${name}: limites ausentes`);
  const actual = compose('exec', '-T', name, 'sh', '-c', 'cat /sys/fs/cgroup/cpu.max /sys/fs/cgroup/memory.max').split(/\s+/);
  assert.notEqual(actual[0], 'max', `${name}: CPU sem limite efetivo`);
  assert.notEqual(actual[2], 'max', `${name}: memória sem limite efetivo`);
  assert.equal(Number(actual[0]) / Number(actual[1]), cpu / 1e9, `${name}: quota CPU diferente do Compose`);
  assert.equal(Number(actual[2]), memory, `${name}: limite memória diferente do Compose`);
  nanoCpus += cpu;
  memoryBytes += memory;
  limits[name] = { cpus: cpu / 1e9, memoryBytes: memory, cgroupCpuMax: `${actual[0]} ${actual[1]}` };
}
assert.ok(nanoCpus <= 1.5e9, `CPU excede 1,5: ${nanoCpus / 1e9}`);
assert.ok(memoryBytes <= 3e9, `Memória excede 3GB decimais: ${memoryBytes}`);
console.log(JSON.stringify({ limits, totalCpus: nanoCpus / 1e9, totalMemoryBytes: memoryBytes, cgroupVersion: 2 }, null, 2));
