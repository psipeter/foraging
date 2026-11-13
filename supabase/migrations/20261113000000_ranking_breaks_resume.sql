-- Resuming a session with ranking breaks: server.resume_state also returns held_seconds (the time the session clock was held in breaks, so the game continues the
-- foraging clock from clock - held_seconds), breaks (begun, so the numbering continues), sets_played (so the pool continues) and break_bonus (the sets' hidden bonus so far,
-- for the end screen's total; the run's points sum it with the score as before). Otherwise unchanged.

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
        'is_interlude', s.is_interlude,
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
        'break_bonus', coalesce((select sum(bonus) from public.interlude_trials where run_id = p_run and session_index = s.session_index and not s.is_interlude), 0),
        'sets_played', (select count(*) from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_set'),
        'running_total', coalesce((select running_total from public.events
                                   where run_id = p_run and session_index = s.session_index and type = 'fruit' order by seq desc limit 1), 0),
        -- fruits already taken per bush (the k-th fruit pays the pre-drawn fruit_reward[bush][k])
        'fruits_taken', coalesce((select jsonb_agg(jsonb_build_object('tree', tree_id, 'n', n) order by tree_id) from (
                                     select tree_id, count(*) as n from public.events
                                     where run_id = p_run and session_index = s.session_index and type = 'fruit' group by tree_id) f), '[]'::jsonb),
        'open_bout_tree', coalesce(case when last_bout.type = 'harvest_press' then last_bout.tree_id end, -1),
        'interlude_plan', coalesce((select trial_order from public.interlude_plan where run_id = p_run and session_index = s.session_index), '[]'::jsonb),
        -- the current Interlude's finished trials, for its tally
        'trial_rows', case when s.is_interlude and not s.completed then coalesce((select jsonb_agg(jsonb_build_object(
                                 'correct', coalesce(choice_correct, 0), 'bonus', coalesce(bonus, 0)) order by seq)
                             from public.interlude_trials where run_id = p_run and session_index = s.session_index), '[]'::jsonb)
                          else '[]'::jsonb end,
        -- earlier sessions, for the running totals on the final screen
        'previous', coalesce((select jsonb_agg(jsonb_build_object('index', session_index, 'is_practice', is_practice,
                                 'is_interlude', is_interlude, 'score', coalesce(final_score, 0)) order by session_index)
                              from public.sessions where run_id = p_run and completed), '[]'::jsonb),
        'previous_interlude', (select jsonb_build_object('trials', count(t.*), 'correct', coalesce(sum(coalesce(t.choice_correct, 0)), 0),
                                                         'bonus', coalesce(sum(coalesce(t.bonus, 0)), 0))
                               from public.interlude_trials t join public.sessions z using (run_id, session_index)
                               where t.run_id = p_run and z.completed and z.is_interlude and not z.is_practice),
        'gap_seconds', coalesce(extract(epoch from now() - last_seen), 0))
        || server.stream_state(p_run, s.session_index);
end $$;

-- The points of a run (menu, finish_run): the ranking breaks' sets are rows of interlude_trials of a foraging session, so the bonus of a completed, non-practice
-- session's sets counts whether or not the session is an Interlude (before, only an Interlude's trials were summed). Nothing else changes.
create or replace function server.run_points(p_run uuid) returns numeric
language sql stable as $$
    select coalesce((select sum(s.final_score) from public.sessions s
                     where s.run_id = p_run and s.completed and not s.is_interlude and not s.is_practice), 0)
         + coalesce((select sum(coalesce(t.bonus, 0)) from public.interlude_trials t
                     join public.sessions s on s.run_id = t.run_id and s.session_index = t.session_index
                     where t.run_id = p_run and s.completed and not s.is_practice), 0);
$$;
