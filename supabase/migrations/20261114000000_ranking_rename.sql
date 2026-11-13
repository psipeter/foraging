-- The cleanup that removed the Interlude (docs/CLEANUP_PLAN.md): a session is foraging with ranking sets played in place, and nothing is called an Interlude.
--   * interlude_trials becomes ranking_sets, one row per ranking set, keeping only the columns a set uses:
--       set_index (sets played before it in the session), pool_index (its place in the session's pool file), start_x and start_z (where the player stood),
--       timed_out, response_time (seconds from the set's start to its last pick), first_harvest_time, bonus, paused_seconds, set_size, correct_pairs, total_pairs,
--       bushes (jsonb, one object per bush)
--     the pair columns (left_*, right_*, correct_side, choice, ...) are dropped; seq, set_size, correct_pairs, total_pairs, bonus and bushes keep their meaning.
--   * interlude_plan (the shuffled trial order of an Interlude) and the view interlude_picks (now ranking_picks) go; sessions loses is_interlude, interlude_file and
--     interlude_sha256.
--   * the upload's `trials` become `sets` (stream_state's trials_next is sets_next, the gap error gap_trials is gap_sets); resume_state loses the Interlude's fields.
-- Back up the database first (scripts/db_backup.py): the dropped columns held the old experiments' pair trials.

drop view public.interlude_picks;
drop table public.interlude_plan;

alter table public.interlude_trials rename to ranking_sets;
alter table public.ranking_sets rename constraint interlude_trials_pkey to ranking_sets_pkey;
alter table public.ranking_sets rename constraint interlude_trials_run_id_session_index_fkey to ranking_sets_run_id_session_index_fkey;
alter table public.ranking_sets rename column presented_order to set_index;
alter table public.ranking_sets rename column trial_index to pool_index;
alter table public.ranking_sets rename column stage_x to start_x;
alter table public.ranking_sets rename column stage_z to start_z;
alter table public.ranking_sets
    drop column type, drop column varied_feature,
    drop column left_id, drop column left_shape, drop column left_color, drop column left_moisture, drop column left_value,
    drop column right_id, drop column right_shape, drop column right_color, drop column right_moisture, drop column right_value,
    drop column correct_side, drop column choice, drop column choice_correct, drop column first_harvest_side,
    drop column left_fruits, drop column right_fruits, drop column locked_at;

alter table public.sessions drop column is_interlude, drop column interlude_file, drop column interlude_sha256;

-- The long form: one row per bush of each set (the table stays deny-all; the view is read with the owner's rights only).
create view public.ranking_picks with (security_invoker = true) as
select t.run_id, t.session_index, t.seq, t.set_index, t.pool_index, t.set_size,
       (b ->> 'id')::integer              as bush_id,
       (b ->> 'slot')::integer            as slot,
       (b ->> 'shape')::double precision  as shape,
       (b ->> 'color')::double precision  as color,
       (b ->> 'moisture')::double precision as moisture,
       (b ->> 'value')::double precision  as value,
       (b ->> 'rank')::integer            as rank,
       (b ->> 'start_time')::double precision  as start_time,
       (b ->> 'finish_time')::double precision as finish_time,
       (b ->> 'fruits')::integer          as fruits
from public.ranking_sets t, jsonb_array_elements(t.bushes) b
where t.bushes is not null;
revoke all on public.ranking_picks from public, anon, authenticated;

-- Where each stream of a session stands: the next sequence number the server expects.
create or replace function server.stream_state(p_run uuid, p_session integer) returns jsonb
language sql stable as $$
    select jsonb_build_object(
        'events_next',     (select coalesce(max(seq) + 1, 0) from public.events where run_id = p_run and session_index = p_session),
        'trajectory_next', (select coalesce(max(first_seq + n_frames), 0) from public.trajectory where run_id = p_run and session_index = p_session),
        'sets_next',       (select coalesce(max(seq) + 1, 0) from public.ranking_sets where run_id = p_run and session_index = p_session));
$$;

-- What a client needs to continue the run's latest session (as before, without the Interlude's order and tallies).
create or replace function server.resume_state(p_run uuid) returns jsonb
language plpgsql stable as $$
declare
    s public.sessions;
    last_chunk public.trajectory;
    last_bout public.events;
    last_event double precision;
    last_seen timestamptz;
    breaks integer;
    ended integer;
    held double precision;
    open_start double precision;
    clock_now double precision;
begin
    select * into s from public.sessions where run_id = p_run order by session_index desc limit 1;
    if not found then
        return null;
    end if;
    select * into last_chunk from public.trajectory where run_id = p_run and session_index = s.session_index order by first_seq desc limit 1;
    select * into last_bout from public.events
        where run_id = p_run and session_index = s.session_index and type in ('harvest_press', 'harvest_release') order by seq desc limit 1;
    select max(t), max(received_at) into last_event, last_seen from public.events where run_id = p_run and session_index = s.session_index;
    last_seen := greatest(last_seen, last_chunk.received_at);
    clock_now := greatest(coalesce((last_chunk.last_frame ->> 't')::double precision, 0), coalesce(last_event, 0));
    -- ranking breaks (RankingBreak): the session clock was held while each ran, so the foraging clock is the logged clock minus the time held
    select count(*) into breaks from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_break_start';
    select count(*) into ended from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_break_end';
    select coalesce(sum(e.t - b.t), 0) into held
        from (select t, row_number() over (order by seq) as n from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_break_start') b
        join (select t, row_number() over (order by seq) as n from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_break_end') e using (n);
    if breaks > ended then      -- the data stops inside a break, which the resumed game does not continue: held until the last thing the server heard
        select max(t) into open_start from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_break_start';
        held := held + greatest(clock_now - open_start, 0);
    end if;
    return jsonb_build_object(
        'session_index', s.session_index,
        'name', s.name,
        'is_practice', s.is_practice,
        'completed', s.completed,
        'final_score', coalesce(s.final_score, 0),
        'started_at', coalesce(s.started_at::text, ''),
        'has_pose', last_chunk.run_id is not null,
        'pose', coalesce(last_chunk.last_frame, jsonb_build_object('t', 0, 'x', 0, 'z', 0, 'yaw', 0, 'pitch', 0, 'keys', 0)),
        'last_event_t', coalesce(last_event, 0),
        -- the session clock to continue from: later than every frame and event the server holds
        'clock', greatest(coalesce((last_chunk.last_frame ->> 't')::double precision, 0), coalesce(last_event, 0)),
        -- seconds the clock was held in ranking breaks (the foraging clock to continue from is 'clock' minus this), the breaks begun and the sets shown so far
        'held_seconds', held,
        'breaks', breaks,
        'break_bonus', coalesce((select sum(bonus) from public.ranking_sets where run_id = p_run and session_index = s.session_index), 0),
        'sets_played', (select count(*) from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_set'),
        'running_total', coalesce((select running_total from public.events
                                   where run_id = p_run and session_index = s.session_index and type = 'fruit' order by seq desc limit 1), 0),
        -- fruits already taken per bush (the k-th fruit pays the pre-drawn fruit_reward[bush][k])
        'fruits_taken', coalesce((select jsonb_agg(jsonb_build_object('tree', tree_id, 'n', n) order by tree_id) from (
                                     select tree_id, count(*) as n from public.events
                                     where run_id = p_run and session_index = s.session_index and type = 'fruit' group by tree_id) f), '[]'::jsonb),
        'open_bout_tree', coalesce(case when last_bout.type = 'harvest_press' then last_bout.tree_id end, -1),
        -- earlier sessions, for the running totals on the final screen
        'previous', coalesce((select jsonb_agg(jsonb_build_object('index', session_index, 'is_practice', is_practice, 'score', coalesce(final_score, 0))
                                               order by session_index)
                              from public.sessions where run_id = p_run and completed), '[]'::jsonb),
        'gap_seconds', coalesce(extract(epoch from now() - last_seen), 0))
        || server.stream_state(p_run, s.session_index);
end $$;

-- The points of a run (menu, finish_run): the score of its completed, non-practice sessions plus the bonus of their ranking sets.
create or replace function server.run_points(p_run uuid) returns numeric
language sql stable as $$
    select coalesce((select sum(s.final_score) from public.sessions s
                     where s.run_id = p_run and s.completed and not s.is_practice), 0)
         + coalesce((select sum(coalesce(t.bonus, 0)) from public.ranking_sets t
                     join public.sessions s on s.run_id = t.run_id and s.session_index = t.session_index
                     where t.run_id = p_run and s.completed and not s.is_practice), 0);
$$;

-- One upload: optional session row, events, trajectory chunks and ranking sets of one session. All or nothing; a repeat of rows already held is harmless
-- (idempotent), a gap or a conflicting overlap is an error. Trajectory chunks arrive decoded by the Edge Function: {first_seq, n_frames, t_start, t_end, last_frame,
-- data (base64)}.
create or replace function server.append_batch(p_run uuid, p_token_hash text, p_session integer, p_batch jsonb) returns jsonb
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
        if p_session > coalesce((select max(session_index) from public.sessions where run_id = p_run), -1) + 1 then
            raise exception 'session_gap' using errcode = 'P0001';
        end if;
        insert into public.sessions (run_id, session_index, name, is_practice, world_seed, world_file, world_sha256,
                                     config, camera, display, frame_stats, started_at, ended_at, completed, final_score)
        select p_run, p_session, x.name, coalesce(x.is_practice, false), x.world_seed, x.world_file,
               x.world_sha256, x.config, x.camera, x.display, x.frame_stats, x.started_at,
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

    insert into public.ranking_sets
    select * from jsonb_populate_recordset(null::public.ranking_sets,
        (select coalesce(jsonb_agg(x || jsonb_build_object('run_id', p_run, 'session_index', p_session)), '[]'::jsonb)
         from jsonb_array_elements(coalesce(p_batch -> 'sets', '[]'::jsonb)) x))
    on conflict (run_id, session_index, seq) do nothing;
    select count(*), coalesce(max(seq), -1) into n_rows, max_seq from public.ranking_sets where run_id = p_run and session_index = p_session;
    if n_rows <> max_seq + 1 then
        raise exception 'gap_sets' using errcode = 'P0001';
    end if;

    return server.stream_state(p_run, p_session);
end $$;
