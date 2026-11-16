-- A reload no longer restarts the patch-leaving count (2026-11-16): resume_state also returns `leavings`, the number of the last qualifying patch leaving logged
-- (`rank_leaving`), and `leaving_due`, whether that leaving made a ranking due that had not begun, so the 1, 2, 4, 8 schedule continues where it was. (Before, the count
-- restarted from the schedule number of the last break and the leavings since were lost.) Old clients ignore the new fields. No table changes.

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
    open_seq bigint;
    open_payload jsonb;
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
    if breaks > ended then      -- the data stops inside a break: held until the last thing the server heard (the resumed game logs the break's end, aborted, at the resume)
        select t, seq, payload into open_start, open_seq, open_payload from public.events
            where run_id = p_run and session_index = s.session_index and type = 'rank_break_start' order by seq desc limit 1;
        held := held + greatest(clock_now - open_start, 0);
    end if;
    return jsonb_build_object(
        'session_index', s.session_index,
        'name', s.name,
        'is_practice', s.is_practice,
        'completed', s.completed,
        'foraging_points', coalesce(s.foraging_points, 0),
        'started_at', coalesce(s.started_at::text, ''),
        'has_pose', last_chunk.run_id is not null,
        'pose', coalesce(last_chunk.last_frame, jsonb_build_object('t', 0, 'x', 0, 'z', 0, 'yaw', 0, 'pitch', 0, 'keys', 0)),
        'last_event_t', coalesce(last_event, 0),
        -- the session clock to continue from: later than every frame and event the server holds
        'clock', greatest(coalesce((last_chunk.last_frame ->> 't')::double precision, 0), coalesce(last_event, 0)),
        -- seconds the clock was held in ranking breaks (the foraging clock to continue from is 'clock' minus this), the breaks begun and the sets shown so far
        'held_seconds', held,
        -- the number of the last break begun (a break run again after an interruption keeps its number, so this is not the count of rank_break_start events)
        'breaks', coalesce((select max((payload ->> 'break')::integer) from public.events
                            where run_id = p_run and session_index = s.session_index and type = 'rank_break_start'), 0),
        -- a break the data stops inside: its number, the leaving it came at and how many of its sets were scored; 0 when none is open
        'open_break', case when breaks > ended then coalesce((open_payload ->> 'break')::integer, breaks) else 0 end,
        'open_break_leaving', case when breaks > ended then coalesce((open_payload ->> 'leaving')::integer, 0) else 0 end,
        'open_break_sets_done', case when breaks > ended then (select count(*) from public.events
                                     where run_id = p_run and session_index = s.session_index and type = 'rank_set_end' and seq > open_seq) else 0 end,
        'ranking_points', coalesce((select sum(points) from public.ranking_sets where run_id = p_run and session_index = s.session_index), 0),
        'sets_played', (select count(*) from public.events where run_id = p_run and session_index = s.session_index and type = 'rank_set'),
        'running_total', coalesce((select running_total from public.events
                                   where run_id = p_run and session_index = s.session_index and type = 'fruit' order by seq desc limit 1), 0),
        -- fruits already taken per bush (the k-th fruit pays the pre-drawn fruit_reward[bush][k])
        'fruits_taken', coalesce((select jsonb_agg(jsonb_build_object('tree', tree_id, 'n', n) order by tree_id) from (
                                     select tree_id, count(*) as n from public.events
                                     where run_id = p_run and session_index = s.session_index and type = 'fruit' group by tree_id) f), '[]'::jsonb),
        -- the tutorial hints already shown in this session (their ids, as logged by `hint_shown`): a resumed game does not show them again
        'hints_shown', coalesce((select jsonb_agg(h.id order by h.first_seq) from (
                                    select payload ->> 'id' as id, min(seq) as first_seq from public.events
                                    where run_id = p_run and session_index = s.session_index and type = 'hint_shown' and payload ->> 'id' is not null group by 1) h), '[]'::jsonb),
        -- the patch leavings counted so far (the `rank_leaving` events, numbered from 1) and whether the last one made a ranking due that has not begun: the schedule
        -- (SessionConfig.rankingLeavings) continues from them, so a reload does not start the count again
        'leavings', coalesce((select max((payload ->> 'n')::integer) from public.events
                              where run_id = p_run and session_index = s.session_index and type = 'rank_leaving'), 0),
        'leaving_due', coalesce((select (l.payload ->> 'due')::boolean and l.seq > coalesce((select max(b.seq) from public.events b
                                         where b.run_id = p_run and b.session_index = s.session_index and b.type = 'rank_break_start'), -1)
                                 from public.events l where l.run_id = p_run and l.session_index = s.session_index and l.type = 'rank_leaving'
                                 order by l.seq desc limit 1), false),
        'open_bout_tree', coalesce(case when last_bout.type = 'harvest_press' then last_bout.tree_id end, -1),
        -- earlier sessions, for the running totals on the final screen
        'previous', coalesce((select jsonb_agg(jsonb_build_object('index', session_index, 'is_practice', is_practice, 'foraging_points', coalesce(foraging_points, 0), 'ranking_points', coalesce(ranking_points, 0))
                                               order by session_index)
                              from public.sessions where run_id = p_run and completed), '[]'::jsonb),
        'gap_seconds', coalesce(extract(epoch from now() - last_seen), 0))
        || server.stream_state(p_run, s.session_index);
end $$;
