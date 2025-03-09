select p.contents
  from prompts as p
  join branches as b on p.branch_suffix = b.suffix
  where b.repo_path = :repo_path and b.suffix = :branch_suffix
  order by p.created_at desc
  limit 1;
