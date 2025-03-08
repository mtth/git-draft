insert into prompts (branch_suffix, bot_class, contents)
  values (:branch_suffix, :bot_class, :contents)
  returning id;
