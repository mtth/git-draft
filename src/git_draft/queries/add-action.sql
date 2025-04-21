insert into actions (
    commit_sha,
    prompt_id,
    bot_class,
    walltime_seconds,
    request_count,
    token_count)
  values (
    :commit_sha,
    :prompt_id,
    :bot_class,
    :walltime_seconds,
    :request_count,
    :token_count);
