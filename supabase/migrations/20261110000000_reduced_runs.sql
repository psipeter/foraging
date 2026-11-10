-- Reduced runs (2026-11-10): a development build may play fewer sessions than the experiment lists (the game's `short` and `repeats` knobs, docs/DECISIONS.md
-- "Reduced runs"), and such a run must still be able to finish, so that the finish screen, the completion code and the menu can be tested.
--  * releases.development: the release was registered from a development build (server_admin publish reads it from the build's build_info.json). Only a
--    development release may start a reduced run; a release build can never be talked into one.
--  * runs.expected_sessions: the sessions (practice, sessions, Interludes) a reduced run declared at run-start; null for a full run. finish_run checks
--    against it instead of the release's count, and the menu's n_sessions (hence its progress) follows it.
alter table public.releases add column development boolean not null default false;
alter table public.runs add column expected_sessions integer;

create or replace function server.menu(p_participant uuid, p_commit text) returns jsonb
language sql stable as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'code', e.code,
        'title', e.title,
        'n_sessions', coalesce(r.expected_sessions, re.n_sessions),
        'status', coalesce(r.status, 'none'),
        'sessions_done', coalesce((select count(*) from public.sessions s where s.run_id = r.run_id and s.completed), 0),
        'points', server.run_points(r.run_id),
        'unlocked', not exists (select 1 from unnest(e.requires) q
                                where not exists (select 1 from public.runs f
                                                  where f.participant_id = p_participant and f.experiment = q and f.status = 'finished'))
    ) order by e.sort_order, e.code), '[]'::jsonb)
    from public.release_experiments re
    join public.experiments e on e.code = re.experiment
    left join public.runs r on r.participant_id = p_participant and r.experiment = e.code
    where re.build_commit = p_commit;
$$;

drop function server.start_run(text, uuid, text, text, jsonb);
create function server.start_run(p_run_token_hash text, p_participant uuid, p_participant_token_hash text, p_experiment text, p_build jsonb, p_expected integer default null)
returns jsonb
language plpgsql as $$
declare
    commit text := p_build ->> 'commit';
    r public.runs;
    e public.experiments;
    rid uuid;
    n integer;
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
    if p_expected is not null then
        -- a reduced run: only a build registered as a development release may play one, and never more sessions than the experiment has
        select re.n_sessions into n from public.release_experiments re where re.build_commit = commit and re.experiment = p_experiment;
        if not (select development from public.releases where build_commit = commit) then
            raise exception 'reduced_run_not_allowed' using errcode = 'P0001';
        end if;
        if p_expected < 1 or p_expected > n then
            raise exception 'reduced_run_not_allowed' using errcode = 'P0001';
        end if;
    end if;
    select run_id into rid from public.runs where participant_id = p_participant and experiment = p_experiment;
    if found then
        perform pg_advisory_xact_lock(hashtextextended(rid::text, 0));   -- wait for an upload of the run that is still committing (lock first, then the row)
        select * into r from public.runs where run_id = rid for update;
        if r.status <> 'in_progress' then
            return jsonb_build_object('run_id', r.run_id, 'status', r.status, 'experiment', p_experiment,
                                      'completion_code', case when r.status = 'finished' then coalesce(e.completion_code, 'DUMMY-COMPLETION-CODE') end);
        end if;
        update public.runs set token_hash = p_run_token_hash, expected_sessions = p_expected,
            build_commits = case when commit = any (build_commits) then build_commits else array_append(build_commits, commit) end
            where run_id = rid;
    else
        if exists (select 1 from unnest(e.requires) q
                   where not exists (select 1 from public.runs f where f.participant_id = p_participant and f.experiment = q and f.status = 'finished')) then
            raise exception 'prerequisite_unmet' using errcode = 'P0001';
        end if;
        insert into public.runs (token_hash, platform, build_commit, build_commits, build_dirty, unity_version, participant_id, experiment, expected_sessions)
            values (p_run_token_hash, p_build ->> 'platform', commit, array[commit], (p_build ->> 'dirty')::boolean, p_build ->> 'unity_version',
                    p_participant, p_experiment, p_expected)
            returning run_id into rid;
    end if;
    return jsonb_build_object('run_id', rid, 'status', 'in_progress', 'experiment', p_experiment, 'resume', server.resume_state(rid));
end $$;

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
    select coalesce(r.expected_sessions, re.n_sessions), coalesce(e.completion_code, 'DUMMY-COMPLETION-CODE') into expected, code
        from public.runs r
        join public.experiments e on e.code = r.experiment
        left join public.release_experiments re on re.build_commit = r.build_commit and re.experiment = r.experiment
        where r.run_id = p_run;
    select count(*) into have from public.sessions where run_id = p_run;
    if expected is null then
        problems := problems || jsonb_build_array('the run''s build no longer lists this experiment');
    elsif have <> expected then
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
    -- the completion code goes only to a run the database confirms finished
    return jsonb_build_object('ok', jsonb_array_length(problems) = 0, 'problems', problems,
                              'completion_code', case when jsonb_array_length(problems) = 0 then code end,
                              'points', server.run_points(p_run));
end $$;

revoke all on all functions in schema server from public, anon, authenticated;
