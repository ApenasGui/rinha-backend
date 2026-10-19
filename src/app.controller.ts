import { BadRequestException, Body, Controller, Get, Header, Inject, NotFoundException, Param, Post, Query, Res } from '@nestjs/common';
import { FastifyReply } from 'fastify';
import { isUuid, Pessoa, validatePessoa } from './pessoa';
import { PessoasService } from './pessoas.service';

@Controller()
export class AppController {
  constructor(@Inject(PessoasService) private readonly pessoas: PessoasService) {}

  @Post('pessoas')
  async create(@Body() body: unknown, @Res({ passthrough: true }) reply: FastifyReply): Promise<void> {
    const id = await this.pessoas.create(validatePessoa(body));
    reply.header('Location', `/pessoas/${id}`);
  }

  @Get('pessoas/:id')
  async find(@Param('id') id: string): Promise<Pessoa> {
    if (!isUuid(id)) throw new NotFoundException();
    const pessoa = await this.pessoas.find(id);
    if (pessoa === undefined) throw new NotFoundException();
    return pessoa;
  }

  @Get('pessoas')
  search(@Query('t') term: unknown): Promise<Pessoa[]> {
    if (typeof term !== 'string' || term.length === 0 || term.includes('\0')) {
      throw new BadRequestException('Informe o termo t');
    }
    return this.pessoas.search(term);
  }

  @Get('contagem-pessoas')
  @Header('Content-Type', 'text/plain; charset=utf-8')
  count(): Promise<string> {
    return this.pessoas.count();
  }

  @Get('health')
  health(): Promise<{ status: string }> {
    return this.pessoas.health();
  }
}
