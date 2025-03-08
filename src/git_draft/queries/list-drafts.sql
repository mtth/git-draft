select
    'draft/' || b.suffix as branch,
    min(b.created_at) as created,
    count(p.id) as prompts,
    round(sum(a.walltime), 1) as walltime,
    count(o.id) as ops
  from branches as b
  join prompts as p on b.suffix = p.branch_suffix
  join actions as a on p.id = a.prompt_id
  join operations as o on a.commit_sha = o.action_commit_sha
  where b.repo_path = :repo_path
  group by b.suffix
  order by created desc;
