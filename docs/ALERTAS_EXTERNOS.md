# Alertas externos: alternativa ao Telegram

O Telegram pode continuar sendo usado como **fonte monitorada** sem precisar ser também o destino dos alertas.

## Recomendação: ntfy

O ntfy é um aplicativo de notificações para Android/iOS e também funciona como PWA. O servidor recebe mensagens por HTTP POST/PUT.

Vantagens para o Promo Monitor:

- aplicativo separado do Telegram;
- notificação push com som/vibração e prioridade;
- implementação simples no worker;
- pode usar o serviço hospedado ou ser auto-hospedado;
- ideal para um canal dedicado apenas aos matches.

Observação de segurança: em `ntfy.sh`, nomes de tópicos não reservados funcionam como um segredo; use um nome longo e imprevisível ou autenticação/self-hosting.

## Alternativa: Discord

Um servidor privado com um canal exclusivo também funciona bem. O worker pode enviar cada match para um webhook do Discord.

Vantagens:

- histórico em formato de chat;
- canal separado;
- aplicativo móvel/desktop;
- webhook simples.

## WeChat

Não é a primeira escolha para este projeto. A automação em contas pessoais não oferece o mesmo fluxo simples que Telegram/Discord/ntfy; integrações oficiais são voltadas a produtos específicos da plataforma.

## Estado no projeto

A versão 2.1 continua enviando o alerta de match para **Mensagens Salvas do Telegram**.

Uma atualização futura pode adicionar um seletor por usuário:

```text
Destino do alerta:
[ ] Telegram
[ ] ntfy
[ ] Discord
```

Para um aplicativo dedicado apenas aos alertas, a recomendação é começar por **ntfy**.
