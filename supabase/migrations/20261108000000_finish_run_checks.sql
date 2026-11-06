-- finish_run, tightened after the review of the experiments work (2026-11-06):
--  * a run whose build no longer lists the experiment (a release re-registered without it) is a problem, not a skipped check: it used to be marked
--    finished however few sessions it held, which unlocked the next experiment;
--  * the completion code is returned only when the database confirms the run finished (it used to be returned with the problems, so a scripted call
--    with nothing played got the real code).
--  * the points of a run are defined once (server.run_points, which the menu and finish_run both use), so the game's completion screen takes them from
--    the server instead of adding them up itself: the score of the run's completed sessions plus the bonus of its Interlude trials, practice
--    sessions and practice Interludes left out (they pay nothing).
create or replace function server.run_points(p_run uuid) returns numeric
language sql stable as $$
    select coalesce((select sum(s.final_score) from public.sessions s
                     where s.run_id = p_run and s.completed and not s.is_interlude and not s.is_practice), 0)
         + coalesce((select sum(coalesce(t.bonus, 0)) from public.interlude_trials t
                     join public.sessions s on s.run_id = t.run_id and s.session_index = t.session_index
                     where t.run_id = p_run and s.completed and s.is_interlude and not s.is_practice), 0);
$$;

create or replace function server.menu(p_participant uuid, p_commit text) returns jsonb
language sql stable as $$
    select coalesce(jsonb_agg(jsonb_build_object(
        'code', e.code,
        'title', e.title,
        'n_sessions', re.n_sessions,
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
