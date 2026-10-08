# Segurança

## Nunca versionar

- `server/.env`
- `SUPABASE_SERVICE_ROLE_KEY`
- `CONFIG_ENCRYPTION_KEY`
- Telegram API Hash
- telefone
- Telethon StringSession
- `*.session`
- `*.db`
- token DuckDNS
- chave SSH/PEM
- senhas

## O que é público por definição no frontend

Um navegador precisa receber:

- URL do Supabase
- Supabase **Publishable Key**
- URL pública da Control API

Esses valores podem ser vistos no DevTools. Segurança do banco depende de Auth + RLS. A `service_role` existe somente no backend.

## Antes de publicar

PowerShell:

```powershell
Get-ChildItem -Recurse -File |
  Select-String -Pattern "SERVICE_ROLE|CONFIG_ENCRYPTION|API_HASH|DUCKDNS|PRIVATE_KEY|BEGIN PRIVATE|sb_secret"
```

Git:

```bash
git status
git diff --cached
```

Se um segredo real já tiver sido publicado, removê-lo do arquivo atual não basta: revogue/rotacione esse segredo. Para segredos reais, considere também reescrever o histórico Git.
