-- Free-text feedback a participant may type on the final screen: one row per run (a second submit replaces the first). Given
-- after the run is finished, so it has its own token check (check_run only accepts runs still in progress).

create table public.feedback (
    run_id     uuid primary key references public.runs (run_id) on delete cascade,
    text       text not null check (char_length(text) between 1 and 5000),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

alter table public.feedback enable row level security;

create function server.save_feedback(p_run uuid, p_token_hash text, p_text text) returns void
language plpgsql as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(p_run::text, 0));
    perform 1 from public.runs where run_id = p_run and token_hash = p_token_hash;
    if not found then
        raise exception 'unauthorized' using errcode = '28000';
    end if;
    insert into public.feedback (run_id, text) values (p_run, p_text)
    on conflict (run_id) do update set text = excluded.text, updated_at = now();
end $$;

revoke all on function server.save_feedback(uuid, text, text) from public, anon, authenticated;
