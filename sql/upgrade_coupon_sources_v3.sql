begin;

-- Novas fontes de busca de cupons.
alter table public.tg_coupons
  drop constraint if exists tg_coupons_source_check;

alter table public.tg_coupons
  add constraint tg_coupons_source_check
  check (source in ('telegram','meliuz','cuponeria','picodi','promobit','manual'));

alter table public.tg_coupon_sites
  alter column sources
  set default array['meliuz','cuponeria','picodi','promobit']::text[];

-- Lojas já cadastradas passam a usar os quatro motores.
update public.tg_coupon_sites
set sources = array(
  select distinct s
  from unnest(
    coalesce(sources, '{}'::text[])
    || array['meliuz','cuponeria','picodi','promobit']::text[]
  ) as s
);

-- Histórico de ocorrências continua em 24h.
-- Cupons de qualquer fonte são removidos fisicamente após 48h.
create or replace function public.tg_cleanup_old_data()
returns void language plpgsql security definer set search_path = public as $$
begin
  delete from public.tg_occurrences
  where occurred_at < now() - interval '24 hours';

  delete from public.tg_coupons
  where last_seen_at < now() - interval '48 hours';
end;
$$;

-- Executa uma limpeza imediata ao aplicar a migração.
select public.tg_cleanup_old_data();

commit;
