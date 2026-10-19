import { Module } from '@nestjs/common';
import { AppController } from './app.controller';
import { PessoasService } from './pessoas.service';

@Module({ controllers: [AppController], providers: [PessoasService] })
export class AppModule {}
