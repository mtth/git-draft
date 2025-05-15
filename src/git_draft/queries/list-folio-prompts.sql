select
    datetime(min(p.created_at), 'localtime') as created,
    coalesce(min(template), '-') as template,
    coalesce(min(a.bot_name), '-') as bot,
    coalesce(round(sum(a.walltime_seconds), 1), 0) as walltime,
    count(o.id) as ops
  from prompts as p
  join folios as f on p.folio_id = f.id
  left join actions as a on p.id = a.prompt_id
  left join operations as o on a.prompt_id = o.prompt_id
  where f.id = :folio_id
  group by p.id
  order by created desc;
