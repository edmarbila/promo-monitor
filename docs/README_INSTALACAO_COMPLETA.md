# Instalação completa — Promo Monitor V2.1

Este guia leva uma instalação nova do zero até o mesmo desenho usado em produção: Supabase + frontend estático + Control API HTTPS + worker Python 24/7.

Todos os valores entre `<...>` são placeholders. Não publique suas chaves privadas.

## 1. Pré-requisitos

- conta GitHub;
- projeto Supabase;
- conta Telegram;
- VM Linux com acesso administrativo;
- domínio/subdomínio apontando para a VM (DuckDNS funciona);
- portas TCP 22, 80 e 443 liberadas na nuvem.

A instalação foi testada em Oracle Linux 9. Outros Linux com systemd funcionam com pequenas adaptações.

## 2. Supabase

Crie um projeto.

No SQL Editor execute:

```text
sql/fresh_install.sql
```

Para instalação nova, esse é o único SQL necessário.

Ele cria as tabelas, índices, RLS, triggers, funções, isolamento multiusuário e limpeza automática.

### Chaves

No painel do Supabase obtenha:

- Project URL;
- Publishable key;
- Service role key.

A service role é segredo e só pode existir no servidor.

### Authentication

Em **Authentication → URL Configuration**, defina o endereço real do frontend.

Exemplo GitHub Pages:

```text
Site URL:
https://<USUARIO>.github.io/<REPOSITORIO>/

Redirect URLs:
https://<USUARIO>.github.io/<REPOSITORIO>/
```

Isso é necessário para recuperação de senha.

## 3. Clonar o projeto localmente

```bash
git clone https://github.com/<USUARIO>/<REPOSITORIO>.git
cd <REPOSITORIO>
```

## 4. Backend local

```bash
cd server
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Gere a chave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Preencha `server/.env`:

```env
SUPABASE_URL=https://<PROJETO>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<SERVICE_ROLE>
SUPABASE_PUBLISHABLE_KEY=<PUBLISHABLE_KEY>
CONFIG_ENCRYPTION_KEY=<FERNET_KEY>

ALLOWED_ORIGINS=http://localhost:8080
CONTROL_API_HOST=0.0.0.0
CONTROL_API_PORT=8787

COUPON_SCAN_MINUTES=30
COUPON_HTTP_TIMEOUT=20
```

Nunca envie esse arquivo ao Git.

### Iniciar localmente

Terminal 1:

```bash
cd server
source .venv/bin/activate
python run_control_api.py
```

Terminal 2:

```bash
cd server
source .venv/bin/activate
python multi_user_worker.py
```

Health:

```bash
curl http://127.0.0.1:8787/health
```

## 5. Frontend local

Copie os valores de `config.example.js` para `config.js`.

Para teste local:

```javascript
window.APP_CONFIG = {
  SUPABASE_URL: "https://<PROJETO>.supabase.co",
  SUPABASE_PUBLISHABLE_KEY: "<PUBLISHABLE_KEY>",
  CONTROL_API_URL: "http://localhost:8787"
};
```

Na raiz:

```bash
python -m http.server 8080
```

Abra:

```text
http://localhost:8080
```

Quando usar frontend local junto com produção, inclua localhost no CORS:

```env
ALLOWED_ORIGINS=https://<USUARIO>.github.io,http://localhost:8080
```

CORS usa a origem, portanto GitHub Pages entra sem o caminho do repositório.

## 6. GitHub Pages

O frontend oficial fica na raiz.

No GitHub:

```text
Settings
→ Pages
→ Build and deployment
→ Deploy from a branch
→ main
→ / (root)
```

Atualize `config.js` com a URL HTTPS real da API.

Exemplo:

```javascript
window.APP_CONFIG = {
  SUPABASE_URL: "https://<PROJETO>.supabase.co",
  SUPABASE_PUBLISHABLE_KEY: "<PUBLISHABLE_KEY>",
  CONTROL_API_URL: "https://<DOMINIO_API>"
};
```

A publishable key foi criada para uso no navegador. Não use service role aqui.

## 7. Criar a VM Oracle/Linux

Crie uma VM Linux.

Libere na Security List/NSG:

```text
TCP 22   SSH
TCP 80   HTTP / emissão TLS
TCP 443  HTTPS
```

A porta 8787 não precisa ficar pública, porque Caddy falará com ela em `127.0.0.1`.

### Dependências

Oracle Linux / RHEL:

```bash
sudo dnf -y update
sudo dnf -y install git curl python3 python3-pip firewalld dnf-plugins-core
sudo systemctl enable --now firewalld
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### Usuário de serviço

```bash
sudo useradd --system --create-home --shell /bin/bash promomonitor || true
sudo mkdir -p /opt/promo-monitor
sudo chown -R promomonitor:promomonitor /opt/promo-monitor
```

Clone:

```bash
sudo -u promomonitor git clone https://github.com/<USUARIO>/<REPOSITORIO>.git /opt/promo-monitor
```

### Ambiente Python

```bash
sudo -u promomonitor python3 -m venv /opt/promo-monitor/.venv
sudo -u promomonitor /opt/promo-monitor/.venv/bin/pip install --upgrade pip
sudo -u promomonitor /opt/promo-monitor/.venv/bin/pip install -r /opt/promo-monitor/server/requirements.txt
```

Crie:

```text
/opt/promo-monitor/server/.env
```

com as mesmas variáveis do ambiente local, mas agora:

```env
ALLOWED_ORIGINS=https://<USUARIO>.github.io
```

Proteja:

```bash
sudo chown promomonitor:promomonitor /opt/promo-monitor/server/.env
sudo chmod 600 /opt/promo-monitor/server/.env
```

Valide Python:

```bash
sudo -u promomonitor /opt/promo-monitor/.venv/bin/python -m py_compile   /opt/promo-monitor/server/control_api.py   /opt/promo-monitor/server/coupon_sources.py   /opt/promo-monitor/server/multi_user_worker.py
```

## 8. systemd 24/7

Os modelos estão em:

```text
deploy/systemd/promo-monitor-api.service
deploy/systemd/promo-monitor-worker.service
```

Instale:

```bash
sudo cp /opt/promo-monitor/deploy/systemd/promo-monitor-api.service /etc/systemd/system/
sudo cp /opt/promo-monitor/deploy/systemd/promo-monitor-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now promo-monitor-api
sudo systemctl enable --now promo-monitor-worker
```

Confira:

```bash
sudo systemctl is-active promo-monitor-api
sudo systemctl is-active promo-monitor-worker
curl http://127.0.0.1:8787/health
```

Esperado:

```text
active
active
{"ok":true,"version":"2.1.0"}
```

Logs:

```bash
sudo journalctl -u promo-monitor-api -n 50 --no-pager
sudo journalctl -u promo-monitor-worker -n 50 --no-pager
```

## 9. DuckDNS

Crie um subdomínio em DuckDNS apontando para o IPv4 público da VM.

Para atualização automática crie, fora do repositório, um script privado:

```bash
mkdir -p ~/.duckdns
chmod 700 ~/.duckdns
cat > ~/.duckdns/update.sh <<'EOF'
#!/bin/bash
curl -fsS "https://www.duckdns.org/update?domains=<SUBDOMINIO>&token=<TOKEN>&ip="   -o "$HOME/.duckdns/last.log"
EOF
chmod 700 ~/.duckdns/update.sh
```

Teste:

```bash
~/.duckdns/update.sh
cat ~/.duckdns/last.log
```

Agende:

```bash
crontab -e
```

Adicione:

```text
*/5 * * * * $HOME/.duckdns/update.sh >/dev/null 2>&1
```

Nunca publique o token DuckDNS.

## 10. Caddy + HTTPS

No Oracle Linux/RHEL:

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf copr enable -y @caddy/caddy
sudo dnf install -y caddy
```

Use `deploy/Caddyfile.example` como base:

```caddyfile
<DOMINIO_API> {
    reverse_proxy 127.0.0.1:8787
}
```

Instale:

```bash
sudo cp /opt/promo-monitor/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
sudo systemctl restart caddy
```

Teste:

```bash
curl https://<DOMINIO_API>/health
```

## 11. Primeiro usuário

1. Crie a conta.
2. Confirme o e-mail se habilitado.
3. Entre.
4. O popup **Configure a conexão do Telegram** será exibido.
5. Clique em **Configurar conexão**.
6. O painel abre a aba Telegram.
7. Em `my.telegram.org`, crie uma aplicação em **API development tools**.
8. Informe API ID, API Hash e telefone.
9. Confirme o código e a 2FA, se houver.
10. Aguarde **Conectado**.
11. Cadastre palavras e grupos.

## 12. Palavras-chave

A busca é case-insensitive.

```text
BUG
Bug
bug
```

são consideradas a mesma palavra no banco e na detecção.

## 13. Lojas e cupons

Na aba Lojas digite apenas o nome, por exemplo:

```text
Shopee
Amazon
KaBuM
```

Fontes suportadas:

- Méliuz
- Cuponeria
- Picodi
- Promobit

O botão **Cadastrar e buscar** faz a primeira consulta imediatamente. Em lojas já cadastradas use **Buscar agora**.

O worker repete consultas segundo `COUPON_SCAN_MINUTES`.

## 14. Retenção

```text
Ocorrências Telegram: 24h
Cupons: 48h desde last_seen_at
```

Execução manual:

```sql
select public.tg_cleanup_old_data();
```

## 15. Recuperação de senha

O usuário pode clicar **Esqueci minha senha**.

O Supabase envia o link para a Redirect URL configurada. Ao retornar ao painel, o usuário define a nova senha. Usuários logados também podem trocar a senha na aba **Conta**.

## 16. OCI Run Command opcional

Se não quiser depender de SSH, habilite o plugin de Run Command da instância.

Exemplo de Dynamic Group:

```text
instance.id = '<INSTANCE_OCID>'
```

Policy:

```text
Allow dynamic-group <DYNAMIC_GROUP_NAME> to use instance-agent-command-execution-family in tenancy where request.instance.id=target.instance.id
```

Depois use:

```text
Instância → Gerenciamento → Execução de comando
```

O Run Command pode executar como usuário de agente; use `sudo` quando necessário.

## 17. Atualizar uma VM existente

```bash
cd /opt/promo-monitor
sudo -u promomonitor git pull origin main

sudo -u promomonitor /opt/promo-monitor/.venv/bin/python -m py_compile   /opt/promo-monitor/server/control_api.py   /opt/promo-monitor/server/coupon_sources.py   /opt/promo-monitor/server/multi_user_worker.py

sudo systemctl restart promo-monitor-api
sudo systemctl restart promo-monitor-worker

sudo systemctl is-active promo-monitor-api
sudo systemctl is-active promo-monitor-worker
curl -fsS https://<DOMINIO_API>/health
```

Quando uma atualização trouxer SQL novo, execute apenas a migração indicada no changelog/README. Não rode migrações antigas novamente sem necessidade.

## 18. Backup antes de migrações

Antes de migração estrutural faça backup do Supabase/banco e dos arquivos da VM.

Nunca copie para o repositório:

```text
server/.env
*.session
*.db
*.key
chaves SSH
tokens
backups com credenciais
```

## 19. Checklist final

- frontend abre por HTTPS;
- login funciona;
- recuperação de senha volta ao frontend;
- popup de configuração aparece para conta sem Telegram;
- Telegram conecta;
- worker aparece online;
- grupo pode ser cadastrado;
- palavra pode ser cadastrada;
- match chega;
- loja pode ser cadastrada;
- **Buscar agora** funciona;
- cupons exibem códigos quando a fonte os expõe;
- API retorna versão 2.1.0;
- API e worker estão enabled/active;
- CORS aceita somente seus frontends;
- service role e Fernet key nunca estão no frontend/Git.
