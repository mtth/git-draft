insert into actions (
    prompt_id,
    bot_class,
    walltime_seconds,
    request_count,
    token_count,
    question)
  values (
    :prompt_id,
    :bot_class,
    :walltime_seconds,
    :request_count,
    :token_count,
    :question);
