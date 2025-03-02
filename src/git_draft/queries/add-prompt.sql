insert into prompts (branch_suffix, contents)
  values (:branch_suffix, :contents)
  returning id;
