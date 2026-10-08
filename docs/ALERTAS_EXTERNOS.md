# Alertas pelo ntfy

A partir da versão 2.2, o Telegram continua sendo a **fonte das mensagens monitoradas**, mas os matches de palavras-chave são enviados ao **ntfy**. O worker não envia mais esses alertas para “Mensagens Salvas” do Telegram.

## Como configurar

1. Instale o aplicativo ntfy no celular.
2. Use o servidor padrão **ntfy.sh**; não é necessário criar outro servidor.
3. Entre no Promo Monitor.
4. Abra **Configurar Conexão → Alertas no ntfy**.
5. Copie o tópico mostrado no painel.
6. No ntfy, escolha **Inscrever-se em tópico** e cole exatamente esse tópico.
7. No Promo Monitor, deixe **Ativar alertas pelo ntfy** marcado.
8. Escolha a prioridade.
9. Clique em **Salvar tópico**.
10. Clique em **Enviar teste**.

O botão **Enviar teste não salva, não regenera e não altera o tópico**. Ele envia somente para o tópico que já está salvo no Supabase. Se houver alterações ainda não salvas, o painel pede para salvar antes.

## Tópico

Cada usuário recebe automaticamente um tópico aleatório, mas pode escolher entre dois modos:

### Automático

O sistema gera um tópico seguro, por exemplo:

```text
promo-k4g7x2m9q8v1c6p3d5f0...
```

O botão **Gerar outro automático** cria um novo nome.

### Personalizado

O usuário informa uma base fácil de reconhecer. A base precisa conter pelo menos **uma letra e um número**.

Exemplo informado:

```text
promocao 001
```

O sistema converte espaços/símbolos em hífens e acrescenta uma sequência aleatória de segurança:

```text
promocao-001-k7m4q2x9ab
```

Antes de salvar, o painel mostra a **prévia do tópico final**.

Se o usuário digitar apenas `promocao`, o painel bloqueia o salvamento e informa que também é necessário um número.

No serviço público ntfy.sh, o tópico deve ser tratado como uma senha. Não publique o nome completo em repositórios, grupos ou capturas de tela.

No aplicativo ntfy, use **exatamente o mesmo tópico final** mostrado no Promo Monitor. Se alterar o tópico no painel, atualize também a inscrição no aplicativo.

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
