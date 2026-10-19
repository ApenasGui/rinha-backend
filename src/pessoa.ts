import { BadRequestException, UnprocessableEntityException } from '@nestjs/common';

export interface PessoaInput {
  apelido: string;
  nome: string;
  nascimento: string;
  stack: string[] | null;
}

export interface Pessoa extends PessoaInput {
  id: string;
}

function requiredString(value: unknown, name: string, maxLength?: number): string {
  if (value === null || value === undefined || value === '') {
    throw new UnprocessableEntityException(`${name} é obrigatório`);
  }
  if (typeof value !== 'string') {
    throw new BadRequestException(`${name} deve ser string`);
  }
  // PostgreSQL varchar measures Unicode characters, not UTF-16 code units.
  if (value.includes('\0') || (maxLength !== undefined && value.length > maxLength &&
      [...value].length > maxLength)) {
    throw new UnprocessableEntityException(`${name} inválido`);
  }
  return value;
}

export function isValidDate(value: string): boolean {
  if (value.length !== 10 || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(5, 7));
  const day = Number(value.slice(8, 10));
  if (year < 1 || month < 1 || month > 12 || day < 1) return false;
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= days[month - 1]!;
}

export function validatePessoa(body: unknown): PessoaInput {
  if (body === null || typeof body !== 'object' || Array.isArray(body)) {
    throw new BadRequestException('O corpo deve ser um objeto JSON');
  }
  const input = body as Record<string, unknown>;
  const apelido = requiredString(input.apelido, 'apelido', 32);
  const nome = requiredString(input.nome, 'nome', 100);
  const nascimento = requiredString(input.nascimento, 'nascimento');
  if (!isValidDate(nascimento)) {
    throw new UnprocessableEntityException('nascimento deve ser uma data AAAA-MM-DD válida');
  }
  let stack: string[] | null = null;
  if (input.stack !== null && input.stack !== undefined) {
    if (!Array.isArray(input.stack)) throw new BadRequestException('stack deve ser um array');
    stack = input.stack.map((entry: unknown) => {
      if (typeof entry !== 'string') throw new BadRequestException('stack deve conter strings');
      return requiredString(entry, 'item de stack', 32);
    });
  }
  return { apelido, nome, nascimento, stack };
}

export function escapeLike(term: string): string {
  return `%${term.replace(/[\\%_]/g, '\\$&')}%`;
}

export function isUuid(value: string): boolean {
  return value.length === 36 && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
}
