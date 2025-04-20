select
    datetime(min(p.created_at), 'localtime') as created,
    f.id as id,
    min(f.origin_branch) as origin,
    count(p.id) as prompts,
    sum(a.token_count) as tokens
  from folios as f
  join prompts as p on f.id = p.folio_id
  join actions as a on p.id = a.prompt_id
  where f.repo_uuid = :repo_uuid
  group by f.id
  order by created desc;
