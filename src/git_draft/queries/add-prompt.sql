insert into prompts (branch_suffix, template, contents)
  values (:branch_suffix, :template, :contents)
  returning id;
