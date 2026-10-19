import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HttpException } from '@nestjs/common';
import { escapeLike, isValidDate, validatePessoa } from '../src/pessoa';

const valid = { apelido: 'ana', nome: 'Ana Barbosa', nascimento: '1985-09-23' };
function status(body: unknown, expected: number): void {
  assert.throws(() => validatePessoa(body), (error: unknown) =>
    error instanceof HttpException && error.getStatus() === expected);
}

test('accepts null/omitted stack and preserves input strings', () => {
  assert.deepEqual(validatePessoa(valid), { ...valid, stack: null });
  assert.deepEqual(validatePessoa({ ...valid, stack: null }), { ...valid, stack: null });
  assert.deepEqual(validatePessoa({ ...valid, stack: ['C#', 'Node'] }).stack, ['C#', 'Node']);
});

test('distinguishes missing/invalid values (422) from wrong JSON types (400)', () => {
  for (const key of ['apelido', 'nome', 'nascimento']) {
    for (const value of [undefined, null, '']) status({ ...valid, [key]: value }, 422);
    for (const value of [42, true, [], {}]) status({ ...valid, [key]: value }, 400);
  }
  for (const body of [null, [], 'text', 42]) status(body, 400);
  for (const stack of [42, {}, 'Node', [1, 'PHP'], [null], [false]]) status({ ...valid, stack }, 400);
  status({ ...valid, stack: [''] }, 422);
});

test('enforces character bounds, accepts Unicode characters and rejects NUL', () => {
  assert.equal(validatePessoa({ ...valid, apelido: '😀'.repeat(32) }).apelido.length, 64);
  status({ ...valid, apelido: 'a'.repeat(33) }, 422);
  status({ ...valid, apelido: '😀'.repeat(33) }, 422);
  status({ ...valid, nome: 'a'.repeat(101) }, 422);
  status({ ...valid, stack: ['a'.repeat(33)] }, 422);
  status({ ...valid, nome: 'N\0me' }, 422);
});

test('validates actual calendar dates including leap years and exact ISO format', () => {
  for (const value of ['2000-02-29', '2024-02-29', '0001-01-01', '9999-12-31']) {
    assert.equal(isValidDate(value), true, value);
  }
  for (const value of ['1900-02-29', '2023-02-29', '2024-04-31', '0000-01-01', '2023-13-01',
    '2023-01-00', '23-01-01', '2023-1-01', '2023-01-01T00:00:00Z', '2023-01-01\n']) {
    assert.equal(isValidDate(value), false, value);
    status({ ...valid, nascimento: value }, 422);
  }
});

test('search escapes SQL wildcard characters and backslashes as literal substrings', () => {
  assert.equal(escapeLike('Node'), '%Node%');
  assert.equal(escapeLike('a_b%c\\d'), '%a\\_b\\%c\\\\d%');
  assert.equal(escapeLike("'; DROP TABLE pessoas; --"), "%'; DROP TABLE pessoas; --%");
});
