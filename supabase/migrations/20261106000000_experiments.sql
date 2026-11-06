-- Experiments (docs/DECISIONS.md, "Experiments": the game is experiment-centric). A participant logs in once (an ID and a signature),
-- sees the experiments the build offers, and plays each as its own run: one run per (participant, experiment). A run keeps what it
-- always was (a token, contiguous sessions 0..n-1, resume of its latest session); what is new is the participant above it, the
-- experiment it belongs to, prerequisites between experiments and a completion code per experiment.
--
--   participants          one row per logged-in person; a token of its own (the menu and starting runs; feedback after a finish)
--   pid_registry          Prolific ID -> participant (the ID stays apart from every analysis table)
--   experiments           code (the prefix of its assets), title (what the menu shows), requires (codes finished first), completion code, payout
--   release_experiments   which experiments a build offers and how many sessions (practice, sessions, Interludes) each has
--   runs                  gains participant_id and experiment; unique per pair
--
-- Existing runs (debugging only, no participant data exists) become the experiment 'legacy' of one participant each.

create table public.participants (
    participant_id uuid primary key default gen_random_uuid(),
    token_hash     text,                    -- the participant's bearer secret, replaced at every login
    created_at     timestamptz not null default now()
);

create table public.experiments (
    code            text primary key check (code ~ '^[A-Za-z0-9]{1,32}$'),
    title           text not null,
    requires        text[] not null default '{}',     -- experiment codes the participant must have finished first
    sort_order      integer not null default 0,
    completion_code text,                              -- the Prolific completion code of this experiment (null: a dummy is shown)
    payout          jsonb,                             -- points and payout settings, decided per experiment (not read by the server)
    registered_at   timestamptz not null default now()
);

create table public.release_experiments (
    build_commit text not null references public.releases (build_commit) on delete cascade,
    experiment   text not null references public.experiments (code),
    n_sessions   integer not null check (n_sessions > 0),
    primary key (build_commit, experiment)
);

insert into public.experiments (code, title) values ('legacy', 'Pilot (before experiments)');
insert into public.release_experiments (build_commit, experiment, n_sessions)
    select build_commit, 'legacy', n_sessions from public.releases where n_sessions is not null and n_sessions > 0;

-- Participants of the runs that exist: one per registered Prolific ID, one per run without an ID.
alter table public.pid_registry add column participant_id uuid;
update public.pid_registry set participant_id = gen_random_uuid();
insert into public.participants (participant_id) select participant_id from public.pid_registry;

alter table public.runs add column participant_id uuid references public.participants (participant_id) on delete cascade;
alter table public.runs add column experiment text references public.experiments (code);
update public.runs r set participant_id = p.participant_id from public.pid_registry p where p.run_id = r.run_id;
with loose as (select run_id, gen_random_uuid() as pid from public.runs where participant_id is null),
     made as (insert into public.participants (participant_id) select pid from loose returning participant_id)
update public.runs r set participant_id = loose.pid from loose where loose.run_id = r.run_id;
update public.runs set experiment = 'legacy';
alter table public.runs alter column participant_id set not null;
alter table public.runs alter column experiment set not null;
alter table public.runs add constraint runs_one_per_experiment unique (participant_id, experiment);

alter table public.pid_registry alter column participant_id set not null;
alter table public.pid_registry add constraint pid_registry_participant_key unique (participant_id);
alter table public.pid_registry add constraint pid_registry_participant_fkey
    foreign key (participant_id) references public.participants (participant_id) on delete cascade;
alter table public.pid_registry drop column run_id;

-- Consent belongs to the participant (given once per consent version, at login); a run no longer carries it.
alter table public.consents add column participant_id uuid references public.participants (participant_id) on delete cascade;
update public.consents c set participant_id = r.participant_id from public.runs r where r.run_id = c.run_id;
alter table public.consents alter column participant_id set not null;
alter table public.consents alter column run_id drop not null;
create index consents_participant on public.consents (participant_id, version);

alter table public.participants         enable row level security;
alter table public.experiments          enable row level security;
alter table public.release_experiments  enable row level security;
revoke all on public.participants, public.experiments, public.release_experiments from anon, authenticated;

-- ---------------------------------------------------------------------------------------------------------------------------
-- The menu: every experiment the build offers with the participant's standing in it. `unlocked` is the prerequisite rule
-- (every code in `requires` has a finished run of this participant); run-start enforces it, the menu only shows it.
create function server.menu(p_participant uuid, p_commit text) returns jsonb
language sql stable as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'code', e.code,
        'title', e.title,
        'n_sessions', re.n_sessions,
        'status', coalesce(r.status, 'none'),
        'sessions_done', coalesce((select count(*) from public.sessions s where s.run_id = r.run_id and s.completed), 0),
        'unlocked', not exists (select 1 from unnest(e.requires) q
                                where not exists (select 1 from public.runs f
                                                  where f.participant_id = p_participant and f.experiment = q and f.status = 'finished'))
    ) order by e.sort_order, e.code), '[]'::jsonb)
    from public.release_experiments re
    join public.experiments e on e.code = re.experiment
    left join public.runs r on r.participant_id = p_participant and r.experiment = e.code
    where re.build_commit = p_commit;
$$;

-- Checks the participant's token and serializes that participant's requests.
create function server.check_participant(p_participant uuid, p_token_hash text) returns void
language plpgsql as $$
begin
    perform pg_advisory_xact_lock(hashtextextended('participant:' || p_participant::text, 0));
    perform 1 from public.participants where participant_id = p_participant and token_hash = p_token_hash;
    if not found then
        raise exception 'unauthorized' using errcode = '28000';
    end if;
end $$;

-- The login: a known or new participant gets a fresh token (the previous one stops working) and the menu.
-- `p_version` is the consent text's version the client holds; when it is given and the participant has no consent of that version on
-- file, the answer is {needs_consent: true} and nothing is created or issued until a call with `p_consent` {version, signature, at}.
-- Without a version (a development build with no consent screen) no consent is asked.
create function server.start_participant(p_token_hash text, p_build jsonb, p_pid text, p_version text, p_consent jsonb default null)
returns jsonb
language plpgsql as $$
declare
    commit text := p_build ->> 'commit';
    pid uuid;
begin
    if commit is null or not exists (select 1 from public.releases where build_commit = commit) then
        raise exception 'unknown_build' using errcode = 'P0001';
    end if;
    if p_pid is not null then
        perform pg_advisory_xact_lock(hashtextextended('pid:' || p_pid, 0));
        select participant_id into pid from public.pid_registry where prolific_pid = p_pid;
    end if;
    if p_version is not null and p_consent is null
       and (pid is null or not exists (select 1 from public.consents where participant_id = pid and version = p_version)) then
        return jsonb_build_object('needs_consent', true);
    end if;
    if pid is null then
        insert into public.participants (token_hash) values (p_token_hash) returning participant_id into pid;
        if p_pid is not null then
            insert into public.pid_registry (prolific_pid, participant_id) values (p_pid, pid);
        end if;
    else
        perform pg_advisory_xact_lock(hashtextextended('participant:' || pid::text, 0));
        update public.participants set token_hash = p_token_hash where participant_id = pid;
    end if;
    if p_consent is not null and not exists (select 1 from public.consents where participant_id = pid and version = p_consent ->> 'version') then
        insert into public.consents (participant_id, version, signature, client_time)
            values (pid, p_consent ->> 'version', p_consent ->> 'signature', (p_consent ->> 'at')::timestamptz);
    end if;
    return jsonb_build_object('needs_consent', false, 'participant_id', pid, 'experiments', server.menu(pid, commit));
end $$;

-- A new run of an experiment, or the continuation of the participant's unfinished one (a fresh run token; the old one stops working).
-- A finished run is not restarted: the answer is its status and completion code. Prerequisites are checked when a run is created.
drop function server.start_run(text, jsonb, text, jsonb);
create function server.start_run(p_run_token_hash text, p_participant uuid, p_participant_token_hash text, p_experiment text, p_build jsonb)
returns jsonb
language plpgsql as $$
declare
    commit text := p_build ->> 'commit';
    r public.runs;
    e public.experiments;
    rid uuid;
begin
    perform server.check_participant(p_participant, p_participant_token_hash);
    if commit is null or not exists (select 1 from public.releases where build_commit = commit) then
        raise exception 'unknown_build' using errcode = 'P0001';
    end if;
    select ex.* into e from public.experiments ex
        join public.release_experiments re on re.experiment = ex.code and re.build_commit = commit where ex.code = p_experiment;
    if not found then
        raise exception 'unknown_experiment' using errcode = 'P0001';
    end if;
    select run_id into rid from public.runs where participant_id = p_participant and experiment = p_experiment;
    if found then
        perform pg_advisory_xact_lock(hashtextextended(rid::text, 0));   -- wait for an upload of the run that is still committing (lock first, then the row)
        select * into r from public.runs where run_id = rid for update;
        if r.status <> 'in_progress' then
            return jsonb_build_object('run_id', r.run_id, 'status', r.status, 'experiment', p_experiment,
                                      'completion_code', case when r.status = 'finished' then coalesce(e.completion_code, 'DUMMY-COMPLETION-CODE') end);
        end if;
        update public.runs set token_hash = p_run_token_hash,
            build_commits = case when commit = any (build_commits) then build_commits else array_append(build_commits, commit) end
            where run_id = rid;
    else
        if exists (select 1 from unnest(e.requires) q
                   where not exists (select 1 from public.runs f where f.participant_id = p_participant and f.experiment = q and f.status = 'finished')) then
            raise exception 'prerequisite_unmet' using errcode = 'P0001';
        end if;
        insert into public.runs (token_hash, platform, build_commit, build_commits, build_dirty, unity_version, participant_id, experiment)
            values (p_run_token_hash, p_build ->> 'platform', commit, array[commit], (p_build ->> 'dirty')::boolean, p_build ->> 'unity_version',
                    p_participant, p_experiment)
            returning run_id into rid;
    end if;
    return jsonb_build_object('run_id', rid, 'status', 'in_progress', 'experiment', p_experiment, 'resume', server.resume_state(rid));
end $$;

-- Marks the run finished when every session of its experiment in its build is present and complete; otherwise lists what is missing.
-- The completion code is returned either way: missing data is the researcher's problem, not a reason to withhold the payment.
create or replace function server.finish_run(p_run uuid, p_token_hash text) returns jsonb
language plpgsql as $$
declare
    problems jsonb := '[]'::jsonb;
    expected integer;
    code text;
    have integer;
    s record;
begin
    perform server.check_run(p_run, p_token_hash);
    select re.n_sessions, coalesce(e.completion_code, 'DUMMY-COMPLETION-CODE') into expected, code
        from public.runs r
        join public.experiments e on e.code = r.experiment
        left join public.release_experiments re on re.build_commit = r.build_commit and re.experiment = r.experiment
        where r.run_id = p_run;
    select count(*) into have from public.sessions where run_id = p_run;
    if expected is not null and have <> expected then
        problems := problems || jsonb_build_array(format('%s sessions present, %s expected', have, expected));
    end if;
    for s in select * from public.sessions where run_id = p_run order by session_index loop
        if not s.completed then
            problems := problems || jsonb_build_array(format('session %s (%s) is not complete', s.session_index, s.name));
        end if;
        if not exists (select 1 from public.events where run_id = p_run and session_index = s.session_index and type = 'session_end') then
            problems := problems || jsonb_build_array(format('session %s (%s) has no session_end event', s.session_index, s.name));
        end if;
        if not exists (select 1 from public.trajectory where run_id = p_run and session_index = s.session_index) then
            problems := problems || jsonb_build_array(format('session %s (%s) has no trajectory', s.session_index, s.name));
        end if;
    end loop;
    if (select max(session_index) from public.sessions where run_id = p_run) is distinct from have - 1 then
        problems := problems || jsonb_build_array('session indices are not contiguous from 0');
    end if;
    if jsonb_array_length(problems) = 0 then
        update public.runs set status = 'finished', finished_at = now() where run_id = p_run;
    end if;
    return jsonb_build_object('ok', jsonb_array_length(problems) = 0, 'problems', problems, 'completion_code', code);
end $$;

-- Feedback may be given with the run's token or with the token of the participant the run belongs to (so it can be given or
-- replaced after the run is finished, from the menu).
create or replace function server.save_feedback(p_run uuid, p_token_hash text, p_text text) returns void
language plpgsql as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(p_run::text, 0));
    perform 1 from public.runs r
        where r.run_id = p_run
          and (r.token_hash = p_token_hash
               or exists (select 1 from public.participants p where p.participant_id = r.participant_id and p.token_hash = p_token_hash));
    if not found then
        raise exception 'unauthorized' using errcode = '28000';
    end if;
    insert into public.feedback (run_id, text) values (p_run, p_text)
    on conflict (run_id) do update set text = excluded.text, updated_at = now();
end $$;

revoke all on all functions in schema server from public, anon, authenticated;
