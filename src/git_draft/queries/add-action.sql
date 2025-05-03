insert into actions (
    prompt_id,
    bot_class,
    walltime_seconds,
    request_count,
    token_count)
  values (
    :prompt_id,
    :bot_class,
    :walltime_seconds,
    :request_count,
    :token_count);
