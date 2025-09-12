select
    datetime(min(p.created_at), 'localtime') as created,
    coalesce(min(template), '-') as template,
    coalesce(min(s.bot_name), '-') as bot,
    coalesce(round(sum(s.walltime_seconds), 1), 0) as walltime,
    count(e.id) as ops
  from prompts as p
  join folios as f on p.folio_id = f.id
  left join action_summaries as s on p.id = s.prompt_id
  left join action_events as e on s.prompt_id = e.prompt_id
  where f.id = :folio_id
  group by p.id
  order by created desc;
