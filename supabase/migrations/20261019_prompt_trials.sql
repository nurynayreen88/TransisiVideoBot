-- Klippo: persistent free prompt trials.
-- Apply this migration to the existing Supabase project before deploying the bot.
create table if not exists public.klippo_prompt_trials (
    telegram_user_id bigint primary key,
    successful_count integer not null default 0
        check (successful_count >= 0 and successful_count <= 3),
    updated_at timestamptz not null default now()
);

alter table public.klippo_prompt_trials enable row level security;
revoke all on public.klippo_prompt_trials from anon, authenticated;
grant all on public.klippo_prompt_trials to service_role;

create or replace function public.klippo_record_prompt_success(p_telegram_user_id bigint)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
    v_count integer;
begin
    insert into public.klippo_prompt_trials (telegram_user_id)
    values (p_telegram_user_id)
    on conflict (telegram_user_id) do nothing;

    update public.klippo_prompt_trials
       set successful_count = successful_count + 1,
           updated_at = now()
     where telegram_user_id = p_telegram_user_id
       and successful_count < 3
    returning successful_count into v_count;

    if v_count is null then
        select successful_count
          into v_count
          from public.klippo_prompt_trials
         where telegram_user_id = p_telegram_user_id;
    end if;

    return coalesce(v_count, 0);
end;
$$;

revoke all on function public.klippo_record_prompt_success(bigint) from public, anon, authenticated;
grant execute on function public.klippo_record_prompt_success(bigint) to service_role;
