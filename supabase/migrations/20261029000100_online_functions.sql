-- Server-side logic of the three Edge Functions (docs/ONLINE_DATA_PLAN.md, section 3), in a schema the public API does
-- not expose. The Edge Functions call these over a direct database connection; nothing here is reachable by anon.
-- Errors are raised with a short code as the message (unauthorized, unknown_build, unknown_world, no_session,
-- session_gap, gap_events, gap_trajectory, overlap_trajectory, gap_trials); the Edge Function maps them to HTTP statuses.

create schema if not exists server;
revoke all on schema server from public, anon, authenticated;

-- Serializes the requests of one run and checks its token (the SHA-256 hex of the bearer secret).
create function server.check_run(p_run uuid, p_token_hash text) returns void
language plpgsql as $$
begin
    perform pg_advisory_xact_lock(hashtextextended(p_run::text, 0));
    perform 1 from public.runs where run_id = p_run and token_hash = p_token_hash and status = 'in_progress';
    if not found then
        raise exception 'unauthorized' using errcode = '28000';
    end if;
end $$;

-- Where each stream of a session stands: the next sequence number the server expects.
create function server.stream_state(p_run uuid, p_session integer) returns jsonb
language sql stable as $$
    select jsonb_build_object(
        'events_next',     (select coalesce(max(seq) + 1, 0) from public.events where run_id = p_run and session_index = p_session),
        'trajectory_next', (select coalesce(max(first_seq + n_frames), 0) from public.trajectory where run_id = p_run and session_index = p_session),
        'trials_next',     (select coalesce(max(seq) + 1, 0) from public.interlude_trials where run_id = p_run and session_index = p_session));
$$;

-- Everything a client needs to continue the run's latest session where it stopped (null before the first session).
create function server.resume_state(p_run uuid) returns jsonb
language plpgsql stable as $$
declare
    s public.sessions;
    last_press public.events;
    last_chunk public.trajectory;
    last_bout public.events;
begin
    select * into s from public.sessions where run_id = p_run order by session_index desc limit 1;
    if not found then
        return null;
    end if;
    select * into last_chunk from public.trajectory where run_id = p_run and session_index = s.session_index order by first_seq desc limit 1;
    select * into last_bout from public.events
        where run_id = p_run and session_index = s.session_index and type in ('harvest_press', 'harvest_release') order by seq desc limit 1;
    return jsonb_build_object(
        'session_index', s.session_index,
        'name', s.name,
        'completed', s.completed,
        'final_score', s.final_score,
        'pose', last_chunk.last_frame,
        'last_event_t', (select max(t) from public.events where run_id = p_run and session_index = s.session_index),
        'running_total', (select running_total from public.events
                          where run_id = p_run and session_index = s.session_index and type = 'fruit' order by seq desc limit 1),
        -- fruits already taken per bush (the k-th fruit pays the pre-drawn fruit_reward[bush][k])
        'fruits_taken', coalesce((select jsonb_object_agg(tree_id::text, n) from (
                                     select tree_id, count(*) as n from public.events
                                     where run_id = p_run and session_index = s.session_index and type = 'fruit' group by tree_id) f), '{}'::jsonb),
        'open_bout_tree', case when last_bout.type = 'harvest_press' then last_bout.tree_id end,
        'interlude_plan', (select trial_order from public.interlude_plan where run_id = p_run and session_index = s.session_index),
        'interlude_trials_done', (select count(*) from public.interlude_trials where run_id = p_run and session_index = s.session_index))
        || server.stream_state(p_run, s.session_index);
end $$;

-- A new run, or the continuation of an existing one: a returning Prolific ID gets a fresh token (the old one stops working).
create function server.start_run(p_token_hash text, p_build jsonb, p_pid text) returns jsonb
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
    return jsonb_build_object('run_id', rid, 'status', 'in_progress', 'resume', server.resume_state(rid));
end $$;

-- Continue an anonymous run with its old token (browser storage), rotating the token.
create function server.resume_run(p_run uuid, p_old_hash text, p_new_hash text, p_build jsonb) returns jsonb
language plpgsql as $$
declare
    commit text := p_build ->> 'commit';
begin
    if commit is null or not exists (select 1 from public.releases where build_commit = commit) then
        raise exception 'unknown_build' using errcode = 'P0001';
    end if;
    perform server.check_run(p_run, p_old_hash);
    update public.runs set token_hash = p_new_hash,
        build_commits = case when commit = any (build_commits) then build_commits else array_append(build_commits, commit) end
        where run_id = p_run;
    return jsonb_build_object('run_id', p_run, 'status', 'in_progress', 'resume', server.resume_state(p_run));
end $$;

-- One upload: optional session row, events, trajectory chunks, Interlude plan and trials of one session. All or nothing;
-- a repeat of rows already held is harmless (idempotent), a gap or a conflicting overlap is an error.
-- Trajectory chunks arrive decoded by the Edge Function: {first_seq, n_frames, t_start, t_end, last_frame, data (base64)}.
create function server.append_batch(p_run uuid, p_token_hash text, p_session integer, p_batch jsonb) returns jsonb
language plpgsql as $$
declare
    s jsonb := p_batch -> 'session';
    c jsonb;
    v_first integer;
    v_n integer;
    chunk_end integer;
    n_rows bigint;
    max_seq integer;
begin
    perform server.check_run(p_run, p_token_hash);

    if s is not null and jsonb_typeof(s) = 'object' then
        if (s ->> 'world_sha256') is not null and not exists (select 1 from public.worlds where sha256 = s ->> 'world_sha256') then
            raise exception 'unknown_world' using errcode = 'P0001';
        end if;
        if (s ->> 'interlude_sha256') is not null and not exists (select 1 from public.worlds where sha256 = s ->> 'interlude_sha256') then
            raise exception 'unknown_world' using errcode = 'P0001';
        end if;
        if p_session > coalesce((select max(session_index) from public.sessions where run_id = p_run), -1) + 1 then
            raise exception 'session_gap' using errcode = 'P0001';
        end if;
        insert into public.sessions (run_id, session_index, name, is_practice, is_interlude, world_seed, world_file, world_sha256,
                                     interlude_file, interlude_sha256, config, camera, display, frame_stats, started_at, ended_at,
                                     completed, final_score)
        select p_run, p_session, x.name, coalesce(x.is_practice, false), coalesce(x.is_interlude, false), x.world_seed, x.world_file,
               x.world_sha256, x.interlude_file, x.interlude_sha256, x.config, x.camera, x.display, x.frame_stats, x.started_at,
               x.ended_at, coalesce(x.completed, false), x.final_score
        from jsonb_populate_record(null::public.sessions, s) x
        on conflict (run_id, session_index) do update set
            ended_at    = coalesce(excluded.ended_at, public.sessions.ended_at),
            completed   = public.sessions.completed or excluded.completed,
            final_score = coalesce(excluded.final_score, public.sessions.final_score),
            frame_stats = coalesce(excluded.frame_stats, public.sessions.frame_stats),
            display     = coalesce(excluded.display, public.sessions.display);
    end if;
    if not exists (select 1 from public.sessions where run_id = p_run and session_index = p_session) then
        raise exception 'no_session' using errcode = 'P0001';
    end if;

    insert into public.events (run_id, session_index, seq, t, real, type, tree_id, k, reward, running_total, payload)
    select p_run, p_session, e.seq, e.t, e.real, e.type, e.tree_id, e.k, e.reward, e.running_total, e.payload
    from jsonb_to_recordset(coalesce(p_batch -> 'events', '[]'::jsonb)) as e(seq integer, t double precision, real double precision,
         type text, tree_id integer, k integer, reward double precision, running_total double precision, payload jsonb)
    on conflict (run_id, session_index, seq) do nothing;
    select count(*), coalesce(max(seq), -1) into n_rows, max_seq from public.events where run_id = p_run and session_index = p_session;
    if n_rows <> max_seq + 1 then
        raise exception 'gap_events' using errcode = 'P0001';
    end if;

    for c in select value from jsonb_array_elements(coalesce(p_batch -> 'trajectory', '[]'::jsonb)) loop
        v_first := (c ->> 'first_seq')::integer;
        v_n := (c ->> 'n_frames')::integer;
        select coalesce(max(t.first_seq + t.n_frames), 0) into chunk_end
            from public.trajectory t where t.run_id = p_run and t.session_index = p_session;
        if v_first > chunk_end then
            raise exception 'gap_trajectory' using errcode = 'P0001';
        elsif v_first < chunk_end then
            -- only an exact repeat of a chunk the server already holds is acceptable
            perform 1 from public.trajectory t where t.run_id = p_run and t.session_index = p_session and t.first_seq = v_first
                and t.n_frames = v_n and t.data = decode(c ->> 'data', 'base64');
            if not found then
                raise exception 'overlap_trajectory' using errcode = 'P0001';
            end if;
        else
            insert into public.trajectory (run_id, session_index, first_seq, n_frames, t_start, t_end, last_frame, data)
            values (p_run, p_session, v_first, v_n, (c ->> 't_start')::double precision, (c ->> 't_end')::double precision,
                    c -> 'last_frame', decode(c ->> 'data', 'base64'));
        end if;
    end loop;

    if p_batch ? 'plan' and jsonb_typeof(p_batch -> 'plan') = 'array' then
        insert into public.interlude_plan (run_id, session_index, trial_order) values (p_run, p_session, p_batch -> 'plan')
        on conflict (run_id, session_index) do nothing;
    end if;

    insert into public.interlude_trials
    select * from jsonb_populate_recordset(null::public.interlude_trials,
        (select coalesce(jsonb_agg(x || jsonb_build_object('run_id', p_run, 'session_index', p_session)), '[]'::jsonb)
         from jsonb_array_elements(coalesce(p_batch -> 'trials', '[]'::jsonb)) x))
    on conflict (run_id, session_index, seq) do nothing;
    select count(*), coalesce(max(seq), -1) into n_rows, max_seq from public.interlude_trials where run_id = p_run and session_index = p_session;
    if n_rows <> max_seq + 1 then
        raise exception 'gap_trials' using errcode = 'P0001';
    end if;

    return server.stream_state(p_run, p_session);
end $$;

-- Marks the run finished when every session of its build is present and complete; otherwise lists what is missing.
create function server.finish_run(p_run uuid, p_token_hash text) returns jsonb
language plpgsql as $$
declare
    problems jsonb := '[]'::jsonb;
    expected integer;
    have integer;
    s record;
begin
    perform server.check_run(p_run, p_token_hash);
    select rel.n_sessions into expected from public.runs r join public.releases rel on rel.build_commit = r.build_commit where r.run_id = p_run;
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
    return jsonb_build_object('ok', jsonb_array_length(problems) = 0, 'problems', problems);
end $$;

revoke all on all functions in schema server from public, anon, authenticated;
