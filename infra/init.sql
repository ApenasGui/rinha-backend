CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE pessoas (
    id UUID PRIMARY KEY,
    apelido VARCHAR(32) NOT NULL UNIQUE,
    nome VARCHAR(100) NOT NULL,
    nascimento VARCHAR(10) NOT NULL,
    stack TEXT[],
    busca TEXT NOT NULL
);

CREATE INDEX pessoas_busca_trgm ON pessoas USING gin (busca gin_trgm_ops);
