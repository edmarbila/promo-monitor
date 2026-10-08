# Promo Monitor

Painel multiusuário para monitorar palavras-chave em grupos do Telegram e organizar promoções e cupons.

## Principais recursos

- Cadastro e login pelo Supabase Auth.
- Dados isolados por usuário usando RLS.
- Cada usuário conecta sua própria conta do Telegram.
- Palavras-chave e grupos configuráveis pelo celular.
- Worker independente do navegador/Windows.
- Histórico com retenção automática de 24 horas.
- Central de cupons:
  - cupons detectados nas mensagens do Telegram;
  - busca em lojas cadastradas no Méliuz;
  - busca em lojas cadastradas na Cuponeria.
- Painel web responsivo.
- Painel Windows sincronizado com o mesmo Supabase.
- Projeto preparado para publicação sem dados pessoais.

## Arquitetura

```text
Painel Web / Windows
        |
        v
Supabase Auth + RLS
        |
        +---------------------------+
        |                           |
        v                           v
Control API                  Banco Supabase
(configura Telegram)        palavras/grupos/cupons
        |                           ^
        v                           |
Credenciais criptografadas         |
        |                           |
        +------> Worker multiusuário+
                  |
                  +--> Telegram
                  +--> Méliuz
                  +--> Cuponeria
```

### Por que o painel não altera `.env`

`.env` é configuração do servidor. Em um sistema compartilhado, gravar o API Hash de cada usuário no mesmo `.env` seria inseguro e inviável.

Na V2, o usuário informa `api_id`, `api_hash` e telefone no painel. A **Control API** recebe esses dados autenticada pelo token do Supabase, criptografa os segredos e salva no backend. O navegador não recebe a sessão Telethon de volta.

## Instalação nova

### 1. Supabase

Crie um projeto e execute:

```text
sql/fresh_install.sql
```

Esse arquivo é o SQL completo da versão atual.

Em **Authentication**, configure o cadastro por e-mail conforme sua preferência. Para uso entre amigos, é recomendável manter confirmação de e-mail.

### 2. Backend

```bash
cd server
python -m venv .venv
```

Ative o ambiente e instale:

```bash
pip install -r requirements.txt
```

Copie:

```text
.env.example -> .env
```

Gere a chave de criptografia:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Preencha:

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_PUBLISHABLE_KEY=
CONFIG_ENCRYPTION_KEY=
ALLOWED_ORIGINS=http://localhost:8080
```

Nunca coloque a `service_role` no painel web.

### 3. Control API

```bash
python run_control_api.py
```

Padrão:

```text
http://localhost:8787
```

### 4. Worker

Em outro terminal:

```bash
python multi_user_worker.py
```

### 5. Painel web

Copie:

```text
web/config.example.js -> web/config.js
```

Preencha:

```javascript
window.APP_CONFIG = {
  SUPABASE_URL: "https://...",
  SUPABASE_PUBLISHABLE_KEY: "sb_publishable_...",
  CONTROL_API_URL: "http://localhost:8787"
};
```

Teste:

```bash
cd web
python -m http.server 8080
```

Abra:

```text
http://localhost:8080
```

## Primeiro acesso de um usuário

1. Clique em **Criar conta**.
2. Confirme o e-mail, se exigido.
3. Entre no painel.
4. Abra **Telegram**.
5. Acesse `my.telegram.org`.
6. Abra **API development tools**.
7. Crie uma aplicação e copie `api_id` e `api_hash`.
8. Informe o telefone com DDI.
9. Clique em **Enviar código**.
10. Digite o código recebido.
11. Se necessário, informe a senha 2FA.
12. Quando aparecer **Conectado**, cadastre palavras e grupos.

## Histórico de 24 horas

A função:

```sql
select public.tg_cleanup_old_data();
```

remove ocorrências com mais de 24 horas.

O SQL tenta agendar essa limpeza a cada hora com `pg_cron`. Se o projeto não permitir o agendamento automático, chame a função com outro scheduler.

## Central de cupons

### Telegram

Mensagens encontradas que parecem conter cupom, código, voucher, OFF ou desconto também são colocadas em `tg_coupons`.

### Sites de cupons

Cadastre uma loja na aba **Lojas**:

```text
Nome: KaBuM
Slug: kabum
Fontes: Méliuz + Cuponeria
```

O worker consulta periodicamente páginas públicas como:

```text
https://www.meliuz.com.br/cupom/kabum
https://www.cuponeria.com.br/cupom-desconto/kabum
```

Os coletores são **best-effort**. Sites de terceiros podem mudar o HTML, passar a exigir JavaScript, limitar acessos ou alterar suas regras. Por isso cada fonte fica isolada em:

```text
server/coupon_sources.py
```

Antes de usar em escala, verifique termos de uso e `robots.txt` das fontes. Se existir API oficial ou parceria, prefira a API em vez de scraping.

## Atualizar um projeto V1 existente

Não execute o upgrade sem backup.

1. Abra:
   `sql/upgrade_v1_to_v2.sql`
2. Troque:
   `REPLACE_WITH_OWNER_UUID`
   pelo UUID do seu usuário atual em Supabase Authentication.
3. Execute o arquivo.
4. Depois execute `sql/fresh_install.sql`.

O segundo arquivo completa triggers, policies, funções e cron da V2.

## Migrar SQLite antigo para uma instalação V2 limpa

Use:

```text
legacy/migrate_sqlite_to_v2.py
```

No `.env` da migração:

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
OWNER_USER_ID=UUID_DO_USUARIO
```

Execute:

```bash
python legacy/migrate_sqlite_to_v2.py "/caminho/telegram_monitor.db"
```

## Painel Windows

```bash
cd desktop
pip install -r requirements.txt
```

Copie `.env.example` para `.env` e configure URL + Publishable Key do mesmo Supabase.

```bash
python desktop_app_v2.py
```

O Windows usa o mesmo login e as mesmas tabelas do site. O visual foi aproximado ao painel web. A configuração inicial do Telegram abre o painel web, evitando guardar o API Hash ou a sessão no desktop.

## Rodar 24/7 no Linux

Há dois exemplos de serviço:

```text
deploy/systemd/promo-monitor-api.service
deploy/systemd/promo-monitor-worker.service
```

Ajuste usuário e caminhos antes de ativar.

## Publicar no GitHub sem seus dados

O projeto inclui `.gitignore`. Antes do primeiro `git push`, confirme que não existem no repositório:

- `.env`
- `web/config.js`
- `*.session`
- `*.db`
- `sb_secret`
- API Hash
- telefone
- senha
- `CONFIG_ENCRYPTION_KEY`

Nunca publique uma sessão Telethon. Uma sessão autenticada pode dar acesso à conta Telegram enquanto for válida.

## Estrutura

```text
promo-monitor/
├── web/
├── server/
├── desktop/
├── sql/
├── legacy/
├── deploy/systemd/
├── README.md
├── LICENSE
└── .gitignore
```
