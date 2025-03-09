select
    datetime(min(p.created_at), 'localtime') as created,
    'draft/' || b.suffix as branch,
    min(b.origin_branch) as origin,
    count(p.id) as prompts,
    sum(a.token_count) as tokens
  from branches as b
  join prompts as p on b.suffix = p.branch_suffix
  join actions as a on p.id = a.prompt_id
  where b.repo_path = :repo_path
  group by b.suffix
  order by created desc;
