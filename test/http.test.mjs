import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import test from 'node:test';

const baseUrl = (process.env.BASE_URL ?? 'http://localhost:9999').replace(/\/$/, '');
const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

function unique(prefix = 'p') {
  return `${prefix}_${randomUUID().replaceAll('-', '').slice(0, 20)}`;
}

function person(overrides = {}) {
  return {
    apelido: unique(),
    nome: 'Pessoa de integração',
    nascimento: '2000-02-29',
    stack: ['Node.js', 'NestJS'],
    ...overrides,
  };
}

async function request(path, options = {}) {
  const { body, ...rest } = options;
  const response = await fetch(`${baseUrl}${path}`, {
    ...rest,
    headers: { ...(body === undefined ? {} : { 'content-type': 'application/json' }), ...rest.headers },
    body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body),
    signal: AbortSignal.timeout(15_000),
  });
  return {
    status: response.status,
    headers: response.headers,
    text: await response.text(),
  };
}

function json(response) {
  assert.match(response.headers.get('content-type') ?? '', /application\/json/i);
  return JSON.parse(response.text);
}

async function create(payload) {
  const response = await request('/pessoas', { method: 'POST', body: payload });
  assert.equal(response.status, 201, response.text);
  const location = response.headers.get('location');
  assert.match(location ?? '', /^\/pessoas\//);
  const id = location.slice('/pessoas/'.length);
  assert.match(id, uuidPattern);
  return { id, location };
}

async function search(term) {
  const response = await request(`/pessoas?t=${encodeURIComponent(term)}`);
  assert.equal(response.status, 200, response.text);
  const people = json(response);
  assert.ok(Array.isArray(people));
  assert.ok(people.length <= 50, `A busca retornou ${people.length} resultados`);
  return people;
}

async function count() {
  const response = await request('/contagem-pessoas');
  assert.ok(response.status >= 200 && response.status < 300, response.text);
  assert.match(response.headers.get('content-type') ?? '', /^text\/plain\b/i);
  assert.match(response.text.trim(), /^\d+$/);
  return Number(response.text.trim());
}

test('POST cria UUID e GET devolve o recurso completo entre as duas instâncias', async () => {
  const payload = person();
  const { id, location } = await create(payload);
  // Repetir através do balanceador também exercita a leitura pela outra API.
  for (let index = 0; index < 6; index += 1) {
    const response = await request(location);
    assert.equal(response.status, 200, response.text);
    assert.deepEqual(json(response), { id, ...payload });
  }
});

test('stack aceita null, ausência e vetor vazio', async () => {
  for (const value of [null, undefined, []]) {
    const payload = person({ stack: value });
    if (value === undefined) delete payload.stack;
    const { id, location } = await create(payload);
    const response = await request(location);
    assert.equal(response.status, 200, response.text);
    assert.deepEqual(json(response), { ...payload, id, stack: value ?? null });
  }
});

test('stack extensa continua válida mesmo quando o registro não entra no cache', async () => {
  const payload = person({ stack: Array.from({ length: 65 }, (_, i) => `tecnologia${i}`) });
  const { id, location } = await create(payload);
  for (let i = 0; i < 4; i += 1) {
    const response = await request(location);
    assert.equal(response.status, 200, response.text);
    assert.deepEqual(json(response), { id, ...payload });
  }
});

test('limites aceitam caracteres Unicode e preservam os valores', async () => {
  const suffix = randomUUID().replaceAll('-', '').slice(0, 8);
  const payload = person({
    apelido: `${'😀'.repeat(24)}${suffix}`,
    nome: 'á'.repeat(100),
    stack: ['🚀'.repeat(32)],
  });
  assert.equal([...payload.apelido].length, 32);
  const { id, location } = await create(payload);
  const response = await request(location);
  assert.equal(response.status, 200, response.text);
  assert.deepEqual(json(response), { id, ...payload });
});

test('campos obrigatórios ausentes ou null retornam 422', async (t) => {
  for (const field of ['apelido', 'nome', 'nascimento']) {
    for (const value of [undefined, null]) {
      await t.test(`${field}: ${value === undefined ? 'ausente' : 'null'}`, async () => {
        const payload = person({ [field]: value });
        if (value === undefined) delete payload[field];
        const response = await request('/pessoas', { method: 'POST', body: payload });
        assert.equal(response.status, 422, response.text);
      });
    }
  }
});

test('strings vazias, limites excedidos e elementos vazios retornam 422', async (t) => {
  const cases = [
    ['apelido vazio', { apelido: '' }],
    ['nome vazio', { nome: '' }],
    ['nascimento vazio', { nascimento: '' }],
    ['apelido com 33 caracteres', { apelido: 'a'.repeat(33) }],
    ['nome com 101 caracteres', { nome: 'a'.repeat(101) }],
    ['stack com 33 caracteres', { stack: ['a'.repeat(33)] }],
    ['stack com elemento vazio', { stack: [''] }],
    ['apelido Unicode com 33 caracteres', { apelido: '😀'.repeat(33) }],
    ['stack Unicode com 33 caracteres', { stack: ['🚀'.repeat(33)] }],
  ];
  for (const [name, overrides] of cases) {
    await t.test(name, async () => {
      const response = await request('/pessoas', { method: 'POST', body: person(overrides) });
      assert.equal(response.status, 422, response.text);
    });
  }
});

test('datas com formato inválido ou impossíveis retornam 422', async (t) => {
  for (const nascimento of ['29/02/2000', '2000-2-29', '2001-02-29', '2000-02-30', '2000-13-01', '2000-00-01', '2000-01-00', '2000-01-01T00:00:00Z']) {
    await t.test(nascimento, async () => {
      const response = await request('/pessoas', { method: 'POST', body: person({ nascimento }) });
      assert.equal(response.status, 422, response.text);
    });
  }
});

test('tipos incompatíveis são rejeitados com 400', async (t) => {
  const cases = [
    ['apelido numérico', { apelido: 123 }],
    ['apelido booleano', { apelido: false }],
    ['nome numérico', { nome: 123 }],
    ['nome objeto', { nome: {} }],
    ['nascimento numérico', { nascimento: 20000101 }],
    ['stack string', { stack: 'Node.js' }],
    ['stack objeto', { stack: {} }],
    ['stack com número', { stack: [1, 'PHP'] }],
    ['stack com null', { stack: [null] }],
    ['stack com vetor', { stack: [[]] }],
  ];
  for (const [name, overrides] of cases) {
    await t.test(name, async () => {
      const response = await request('/pessoas', { method: 'POST', body: person(overrides) });
      assert.equal(response.status, 400, response.text);
    });
  }
});

test('JSON malformado retorna 400', async () => {
  const response = await request('/pessoas', { method: 'POST', body: '{"apelido":' });
  assert.equal(response.status, 400, response.text);
});

test('apelido duplicado retorna 422 e a contagem não aumenta', async () => {
  const before = await count();
  const payload = person();
  const { id } = await create(payload);
  const duplicate = await request('/pessoas', { method: 'POST', body: { ...payload, nome: 'Duplicado' } });
  assert.equal(duplicate.status, 422, duplicate.text);
  assert.equal(await count(), before + 1);
  const response = await request(`/pessoas/${id}`);
  assert.deepEqual(json(response), { id, ...payload });
});

test('criações concorrentes com o mesmo apelido persistem exatamente uma pessoa', async () => {
  const before = await count();
  const payload = person();
  const responses = await Promise.all(Array.from({ length: 12 }, () => request('/pessoas', { method: 'POST', body: payload })));
  assert.equal(responses.filter(({ status }) => status === 201).length, 1);
  assert.equal(responses.filter(({ status }) => status === 422).length, 11);
  assert.equal(await count(), before + 1);
  const results = await search(payload.apelido);
  assert.equal(results.length, 1);
  assert.equal(results[0].apelido, payload.apelido);
});

test('busca encontra substrings sem diferenciar maiúsculas em apelido, nome e stack', async () => {
  const marker = unique('busca').slice(0, 16);
  const payloads = [
    person({ apelido: marker }),
    person({ nome: `Prefixo ${marker} sufixo` }),
    person({ stack: [`Prefixo${marker}Sufixo`] }),
  ];
  const ids = await Promise.all(payloads.map(async (payload) => (await create(payload)).id));
  const results = await search(marker.toUpperCase());
  assert.deepEqual(results.map(({ id }) => id).sort(), ids.sort());
  for (const payload of payloads) {
    const result = results.find(({ apelido }) => apelido === payload.apelido);
    assert.ok(result);
    assert.deepEqual(result, { id: result.id, ...payload });
  }
});

test('busca limita a resposta a 50 resultados', async () => {
  const marker = unique('limite');
  await Promise.all(Array.from({ length: 55 }, () => create(person({ nome: marker }))));
  const results = await search(marker);
  assert.equal(results.length, 50);
  assert.equal(new Set(results.map(({ id }) => id)).size, 50);
  assert.ok(results.every(({ nome }) => nome === marker));
});

test('busca sem resultado devolve lista vazia; ausência de t retorna 400', async () => {
  assert.deepEqual(await search(unique('ausente')), []);
  const response = await request('/pessoas');
  assert.equal(response.status, 400, response.text);
  assert.equal((await request('/pessoas?t=')).status, 400);
});

test('busca não combina o final de um campo com o começo de outro', async () => {
  const marker = unique('campo').slice(0, 14);
  await create(person({ apelido: marker, nome: 'SegundoCampo', stack: ['PrimeiroItem', 'SegundoItem'] }));
  assert.deepEqual(await search(`${marker}\u001fSegundoCampo`), []);
  assert.deepEqual(await search('PrimeiroItem\u001fSegundoItem'), []);
});

test('busca trata percentagem, sublinhado e apóstrofo como texto literal', async () => {
  const marker = unique('literal');
  const cases = [
    [`${marker}%`, `${marker}X`],
    [`${marker}_`, `${marker}Y`],
    [`${marker}' OR 1=1 --`, `${marker}Z`],
    [`${marker}\\`, `${marker}W`],
  ];
  for (const [literal, decoy] of cases) {
    const expected = await create(person({ nome: literal }));
    await create(person({ nome: decoy }));
    const results = await search(literal);
    assert.deepEqual(results.map(({ id }) => id), [expected.id]);
  }
});

test('UUID desconhecido ou malformado retorna 404', async () => {
  for (const id of [randomUUID(), 'nao-e-uuid', '123', "' OR 1=1 --"]) {
    const response = await request(`/pessoas/${encodeURIComponent(id)}`);
    assert.equal(response.status, 404, response.text);
  }
});

test('contagem reflete imediatamente as inserções persistidas', async () => {
  const before = await count();
  const created = await Promise.all(Array.from({ length: 5 }, () => create(person())));
  for (let index = 0; index < 4; index += 1) {
    assert.equal(await count(), before + created.length);
  }
  for (const { location } of created) {
    const response = await request(location);
    assert.equal(response.status, 200, response.text);
  }
});
