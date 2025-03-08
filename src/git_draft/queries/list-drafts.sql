select
    datetime(min(p.created_at), 'localtime') as created,
    'draft/' || b.suffix as branch,
    min(b.origin_branch) as origin,
    count(p.id) as prompts
  from branches as b
  join prompts as p on b.suffix = p.branch_suffix
  where b.repo_path = :repo_path
  group by b.suffix
  order by created desc;
