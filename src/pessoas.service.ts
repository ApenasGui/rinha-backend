import { Injectable, OnApplicationShutdown, OnModuleInit, UnprocessableEntityException } from '@nestjs/common';
import { randomUUID } from 'node:crypto';
import { Pool } from 'pg';
import { escapeLike, Pessoa, PessoaInput } from './pessoa';

const columns = 'id, apelido, nome, nascimento, stack';
const matchingField = `(
  lower(apelido) LIKE lower($1) OR lower(nome) LIKE lower($1) OR
  EXISTS (SELECT 1 FROM unnest(stack) AS item WHERE lower(item) LIKE lower($1))
)`;

function integerEnv(name: string, fallback: number, min: number, max: number): number {
  const input = process.env[name];
  const value = input === undefined ? fallback : Number(input);
  if (!Number.isInteger(value) || value < min || value > max) {
    throw new Error(`${name} deve ser inteiro entre ${min} e ${max}`);
  }
  return value;
}

@Injectable()
export class PessoasService implements OnModuleInit, OnApplicationShutdown {
  private readonly pool = new Pool({
    connectionString: process.env.DATABASE_URL ?? 'postgres://rinha:rinha@localhost:5432/rinha',
    max: integerEnv('DB_POOL_SIZE', 15, 1, 20),
    connectionTimeoutMillis: 10_000,
    idleTimeoutMillis: 30_000,
    statement_timeout: 30_000,
    application_name: process.env.HOSTNAME ?? 'rinha-nestjs',
  });
  private readonly cacheSize = integerEnv('CACHE_SIZE', 10_000, 0, 100_000);
  private readonly cache = new Map<string, Pessoa>();
  private readonly searchMode = process.env.SEARCH_MODE ?? 'indexed';

  constructor() {
    if (this.searchMode !== 'scan' && this.searchMode !== 'indexed') {
      throw new Error('SEARCH_MODE deve ser scan ou indexed');
    }
    // An idle connection error must not terminate Node's process unexpectedly.
    this.pool.on('error', (error: Error) => console.error('PostgreSQL connection:', error.message));
  }

  async onModuleInit(): Promise<void> {
    await this.pool.query('SELECT 1');
  }

  async onApplicationShutdown(): Promise<void> {
    await this.pool.end();
  }

  private remember(pessoa: Pessoa): void {
    if (this.cacheSize === 0) return;
    // The contract does not cap the number of stack items. Large valid records
    // remain durable/queryable, but do not consume the optional per-process cache.
    if (pessoa.stack !== null && pessoa.stack.length > 64) return;
    // FIFO keeps insertion/read cost O(1), with a hard memory bound per replica.
    if (this.cache.size >= this.cacheSize) {
      const oldest = this.cache.keys().next().value;
      if (oldest !== undefined) this.cache.delete(oldest);
    }
    this.cache.set(pessoa.id, pessoa);
  }

  async create(input: PessoaInput): Promise<string> {
    const id = randomUUID();
    try {
      // Autocommit completes before pg resolves: no 201 before durable persistence.
      await this.pool.query({
        name: 'create-pessoa',
        text: `INSERT INTO pessoas (id, apelido, nome, nascimento, stack, busca)
          VALUES ($1, $2::text, $3::text, $4, $5,
            lower(concat_ws(chr(31), $2::text, $3::text, array_to_string($5::text[], chr(31)))))`,
        values: [id, input.apelido, input.nome, input.nascimento, input.stack],
      });
    } catch (error: unknown) {
      if (typeof error === 'object' && error !== null && 'code' in error && error.code === '23505') {
        throw new UnprocessableEntityException('apelido já cadastrado');
      }
      throw error;
    }
    this.remember({ id, ...input });
    return id;
  }

  async find(id: string): Promise<Pessoa | undefined> {
    const cached = this.cache.get(id);
    if (cached !== undefined) return cached;
    const result = await this.pool.query<Pessoa>({
      name: 'find-pessoa',
      text: `SELECT ${columns} FROM pessoas WHERE id = $1`,
      values: [id],
    });
    const pessoa = result.rows[0];
    if (pessoa !== undefined) this.remember(pessoa);
    return pessoa;
  }

  async search(term: string): Promise<Pessoa[]> {
    const indexed = this.searchMode === 'indexed';
    const result = await this.pool.query<Pessoa>({
      name: indexed ? 'search-indexed' : 'search-scan',
      text: `SELECT ${columns} FROM pessoas WHERE
        ${indexed ? 'busca LIKE lower($1) AND' : ''} ${matchingField} LIMIT 50`,
      values: [escapeLike(term)],
    });
    return result.rows;
  }

  async count(): Promise<string> {
    const result = await this.pool.query<{ count: string }>('SELECT count(*)::text AS count FROM pessoas');
    return result.rows[0]!.count;
  }

  async health(): Promise<{ status: string }> {
    await this.pool.query('SELECT 1');
    return { status: 'ok' };
  }
}
