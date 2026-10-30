-- Consent records: one row per visit that ended in a signature (a returning participant signs again; each is kept).
-- Like the Prolific ID, the typed name lives apart from every analysis table, and the table is deny-all for the public roles.
create table public.consents (
    consent_id   bigint generated always as identity primary key,
    run_id       uuid not null references public.runs (run_id) on delete cascade,
    version      text not null,          -- the consent text's version line (StreamingAssets/consent.txt)
    signature    text not null,          -- the name the participant typed
    client_time  timestamptz,            -- the participant's clock when they agreed
    recorded_at  timestamptz not null default now()
);
create index consents_run on public.consents (run_id);
alter table public.consents enable row level security;
revoke all on public.consents from anon, authenticated;

-- start_run gains the consent of this visit (null from a build that has no consent screen).
drop function server.start_run(text, jsonb, text);
create function server.start_run(p_token_hash text, p_build jsonb, p_pid text, p_consent jsonb default null) returns jsonb
language plpgsql as $$
declare
    rid uuid;
    r public.runs;
    commit text := p_build ->> 'commit';
begin
    if commit is null or not exists (select 1 from public.releases where build_commit = commit) then
        raise exception 'unknown_build' using errcode = 'P0001';
    end if;
    if p_pid is not null then
        perform pg_advisory_xact_lock(hashtextextended('pid:' || p_pid, 0));
        select run_id into rid from public.pid_registry where prolific_pid = p_pid;
    end if;
    if rid is not null then
        select * into r from public.runs where run_id = rid for update;
        if r.status <> 'in_progress' then
            return jsonb_build_object('run_id', rid, 'status', r.status);
        end if;
        update public.runs set token_hash = p_token_hash,
            build_commits = case when commit = any (build_commits) then build_commits else array_append(build_commits, commit) end
            where run_id = rid;
    else
        insert into public.runs (token_hash, platform, build_commit, build_commits, build_dirty, unity_version)
            values (p_token_hash, p_build ->> 'platform', commit, array[commit], (p_build ->> 'dirty')::boolean, p_build ->> 'unity_version')
            returning run_id into rid;
        if p_pid is not null then
            insert into public.pid_registry (prolific_pid, run_id) values (p_pid, rid);
        end if;
    end if;
    if p_consent is not null then
        insert into public.consents (run_id, version, signature, client_time)
            values (rid, p_consent ->> 'version', p_consent ->> 'signature', (p_consent ->> 'at')::timestamptz);
    end if;
    return jsonb_build_object('run_id', rid, 'status', 'in_progress', 'resume', server.resume_state(rid));
end $$;
