# SQL do Promo Monitor

## Instalação nova

Execute apenas:

```text
fresh_install.sql
```

Esse arquivo representa o schema completo atual, incluindo as fontes Méliuz, Cuponeria, Picodi e Promobit e retenção de cupons em 48 horas.

## Atualização V1 → atual

1. Faça backup.
2. Abra `upgrade_v1_to_v2.sql`.
3. Troque todas as ocorrências de `REPLACE_WITH_OWNER_UUID` pelo UUID do usuário proprietário dos dados antigos.
4. Execute `upgrade_v1_to_v2.sql`.
5. Execute `fresh_install.sql` para completar policies, triggers e funções atuais.
6. Execute `upgrade_coupon_sources_v3.sql` para garantir as fontes/constraint/retenção em instalações que já tinham tabelas de cupons.

## Atualização V2 antiga → múltiplas fontes

Execute:

```text
upgrade_coupon_sources_v3.sql
```

## Atualização para alertas ntfy

Em uma instalação que já estava funcionando antes da versão 2.2, execute:

```text
upgrade_ntfy_alerts_v4.sql
```

Esse SQL cria um tópico ntfy aleatório por usuário, habilita RLS e deixa o ntfy como destino padrão.

## Atualização para canais ntfy separados e filtro de repetidos

Em uma instalação já existente, execute:

```text
upgrade_ntfy_channels_v5.sql
```

Esse SQL adiciona um tópico ntfy por loja, cria o registro persistente de notificações enviadas e a função atômica usada pelo backend para impedir repetidos.

## Retenção atual

- ocorrências: 24 horas;
- cupons: 48 horas desde `last_seen_at`.

Teste manual:

```sql
select public.tg_cleanup_old_data();
```

Não coloque UUIDs reais, e-mails, telefones ou chaves nos SQLs versionados.


## Erro de schema cache em Lojas

Se o painel mostrar:

```text
Could not find the 'ntfy_topic' column of 'tg_coupon_sites' in the schema cache
```

execute a versão atual de:

```text
upgrade_ntfy_channels_v5.sql
```

Ela adiciona/valida a coluna, cria o trigger que gera o canal ntfy de cada loja e, ao final, executa:

```sql
notify pgrst, 'reload schema';
```

O frontend atual não envia mais `ntfy_topic` durante o cadastro; o banco gera o canal automaticamente.
