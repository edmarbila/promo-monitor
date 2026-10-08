# Promo Monitor V2.2

Monitor multiusuário de palavras-chave do Telegram com painel web, worker 24/7 e central de códigos de cupom.

O projeto usa **Supabase Auth + PostgreSQL/RLS**, **Telethon**, **FastAPI**, um worker Python contínuo e um frontend estático que pode ser publicado no **GitHub Pages**.

## O que já está pronto

- Cadastro, login, recuperação e troca de senha pelo Supabase Auth.
- Popup de primeiro acesso orientando o usuário a configurar o Telegram.
- Cada usuário conecta a própria conta Telegram pelo painel.
- API ID, API Hash, telefone e StringSession ficam no backend; dados sensíveis são criptografados.
- Palavras-chave não diferenciam maiúsculas/minúsculas: `BUG`, `Bug` e `bug` são a mesma busca.
- Grupos e palavras isolados por usuário com RLS.
- Worker continua monitorando mesmo com PC e navegador desligados.
- Alertas dos matches enviados pelo **ntfy**, em aplicativo separado do Telegram.
- Histórico de ocorrências com retenção de 24 horas.
- Central de cupons com código, desconto, descrição/regra e origem quando disponíveis.
- Motores de cupons: Telegram, Méliuz, Cuponeria, Picodi e Promobit.
- Cadastro de lojas como Shopee, Amazon e KaBuM pelo nome.
- Busca imediata ao cadastrar uma loja e botão **Buscar agora**.
- Cupons removidos fisicamente após 48 horas sem atualização.
- Painel responsivo para computador e celular.
- Serviços systemd para API e worker.
- Exemplo de reverse proxy HTTPS com Caddy.
- Cliente Windows legado/opcional.

## Arquitetura

```text
GitHub Pages / navegador
        |
        +----> Supabase Auth + RLS
        |          |
        |          +--> palavras / grupos / histórico / cupons
        |
        +----> Control API HTTPS (FastAPI)
                   |
                   +--> configuração Telegram criptografada
                   +--> busca imediata de cupons
                   |
                   v
              Worker 24/7
              /        \
        Telegram     Fontes de cupons
```

## Instalação rápida

Para uma instalação nova:

1. Crie um projeto no Supabase.
2. Execute **somente** `sql/fresh_install.sql`.
3. Copie `server/.env.example` para `server/.env` e preencha seus valores.
4. Gere `CONFIG_ENCRYPTION_KEY`.
5. Instale `server/requirements.txt`.
6. Configure `config.js` com a URL/publishable key do seu Supabase e a URL HTTPS da Control API.
7. Inicie a Control API e o worker.
8. Publique o frontend.
9. Configure no Supabase as URLs de redirecionamento do frontend.

O tutorial completo, incluindo Oracle Cloud, DuckDNS, Caddy, systemd, firewall, GitHub Pages e atualização, está em:

**[docs/README_INSTALACAO_COMPLETA.md](docs/README_INSTALACAO_COMPLETA.md)**

## SQL

- `sql/fresh_install.sql`: instalação nova completa na versão atual.
- `sql/upgrade_v1_to_v2.sql`: migração de instalação antiga V1.
- `sql/upgrade_coupon_sources_v3.sql`: atualização de instalações V2 antigas para múltiplas fontes + retenção de cupons em 48h.
- `sql/upgrade_ntfy_alerts_v4.sql`: adiciona alertas ntfy em instalações já existentes.
- `sql/README.md`: ordem correta para cada cenário.

Para projeto novo, não execute migrações antigas: use apenas `fresh_install.sql`.

## Frontend

A versão oficial do frontend fica na raiz:

```text
index.html
app.js
style.css
config.js
```

`config.example.js` mostra o formato para uma instalação própria.

A URL do Supabase, a **publishable key** e a URL pública da Control API são configurações de cliente e ficam visíveis para qualquer navegador. Nunca coloque no frontend:

- `SUPABASE_SERVICE_ROLE_KEY`
- `CONFIG_ENCRYPTION_KEY`
- Telegram API Hash
- telefone
- StringSession / arquivos `.session`
- senha ou token DuckDNS
- chave SSH

## Backend local

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell:

```powershell
cd server
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Gere a chave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Inicie a API:

```bash
python run_control_api.py
```

Em outro terminal:

```bash
python multi_user_worker.py
```

Teste:

```text
http://localhost:8787/health
```

## Primeiro acesso

Depois de criar a conta e entrar, o painel mostra **Configure a conexão do Telegram**.

O usuário deve:

1. abrir `my.telegram.org`;
2. acessar **API development tools**;
3. criar uma aplicação;
4. copiar `api_id` e `api_hash`;
5. informar telefone com DDI;
6. confirmar o código do Telegram;
7. informar 2FA, se a conta utilizar;
8. aguardar o status **Conectado**;
9. cadastrar palavras e grupos.

## Cupons

Ao cadastrar uma loja, o backend consulta as fontes selecionadas imediatamente e o worker repete a busca periodicamente.

Somente resultados com código digitável são gravados pelas fontes externas. Quando disponível, também são salvos desconto e descrição/regra.

Sites de terceiros podem alterar URLs, HTML, JavaScript, proteção anti-bot ou termos de uso. O coletor fica isolado em:

```text
server/coupon_sources.py
```

Prefira APIs oficiais/parcerias quando existirem.

## Retenção

- ocorrências Telegram: **24 horas**;
- cupons: **48 horas desde a última confirmação**.

A função é:

```sql
select public.tg_cleanup_old_data();
```

O SQL tenta agendá-la com `pg_cron`.

## Publicação segura

Antes de publicar uma cópia/fork, confira **[SECURITY.md](SECURITY.md)**.

O repositório não deve conter `.env`, banco SQLite, sessão Telegram, service role, chave Fernet, chave SSH, token DuckDNS ou telefone.

## Estrutura

```text
promo-monitor/
├── index.html
├── app.js
├── style.css
├── config.js
├── config.example.js
├── server/
│   ├── .env.example
│   ├── control_api.py
│   ├── multi_user_worker.py
│   ├── coupon_sources.py
│   └── ...
├── sql/
├── deploy/
│   └── systemd/
├── desktop/
├── legacy/
├── docs/
├── SECURITY.md
├── README.md
└── LICENSE
```

## Alertas ntfy

O Telegram é usado como **fonte monitorada**, mas os matches são enviados pelo **ntfy**. Cada usuário possui um tópico aleatório salvo em `tg_alert_settings`.

Na aba **Configurar Conexão → Alertas no ntfy**:

1. copie o tópico;
2. instale o aplicativo ntfy;
3. assine esse tópico;
4. clique em **Enviar teste**.

É possível gerar outro tópico automático ou escolher um nome personalizado. O nome personalizado precisa conter pelo menos uma letra e um número; o sistema normaliza o texto e acrescenta um sufixo aleatório de segurança. Exemplo: `promocao 001` pode virar `promocao-001-k7m4q2x9ab`. Depois de trocar o tópico no painel, inscreva-se no ntfy usando exatamente o mesmo nome.

Veja `docs/ALERTAS_EXTERNOS.md`.

## Atualizações

Depois da instalação inicial, normalmente basta atualizar os arquivos do repositório e reiniciar API/worker. O procedimento está na seção **Atualizar uma VM existente** do guia completo.
