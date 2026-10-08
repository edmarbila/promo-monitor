# Alertas pelo ntfy

A partir da versão 2.2, o Telegram continua sendo a **fonte das mensagens monitoradas**, mas os matches de palavras-chave são enviados ao **ntfy**. O worker não envia mais esses alertas para “Mensagens Salvas” do Telegram.

## Como configurar

1. Instale o aplicativo ntfy no celular.
2. Entre no Promo Monitor.
3. Abra **Telegram → Alertas no ntfy**.
4. Copie o tópico mostrado no painel.
5. No ntfy, escolha **Inscrever-se em tópico** e cole o tópico.
6. No Promo Monitor, deixe **Ativar alertas pelo ntfy** marcado.
7. Escolha a prioridade.
8. Clique em **Salvar**.
9. Clique em **Enviar teste**.

## Tópico

Cada usuário recebe automaticamente um tópico longo e aleatório, parecido com:

```text
promo-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

No serviço público ntfy.sh, o tópico deve ser tratado como uma senha: quem souber o nome consegue tentar assinar o tópico. Não publique o tópico em repositórios, grupos ou capturas de tela.

O botão **Gerar novo tópico** permite trocar o endereço. Depois de gerar um novo, salve e assine o novo tópico no aplicativo.

## Prioridade

O Promo Monitor permite:

- 5 — Máxima;
- 4 — Alta;
- 3 — Normal.

O padrão é **Máxima**, adequado para alertas de palavras-chave.

## Teste

O botão **Enviar teste** chama a Control API autenticada. A API publica uma mensagem de teste em:

```text
https://ntfy.sh/<TOPICO>
```

Se a notificação chegar, a configuração está pronta.

## Segurança

A integração atual usa apenas o serviço público `https://ntfy.sh` para evitar que uma URL personalizada controlada por usuário transforme o backend em um proxy para endereços internos.

Para maior privacidade, uma versão futura pode suportar uma instância ntfy auto-hospedada com allowlist administrativa.
