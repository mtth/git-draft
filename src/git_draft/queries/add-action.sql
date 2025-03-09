insert into actions (
    commit_sha,
    prompt_id,
    bot_name,
    bot_class,
    walltime,
    request_count,
    token_count)
  values (
    :commit_sha,
    :prompt_id,
    :bot_name,
    :bot_class,
    :walltime,
    :request_count,
    :token_count);
