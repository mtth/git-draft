insert into action_summaries (
    prompt_id,
    bot_class,
    walltime_seconds,
    request_count,
    token_count,
    pending_question)
  values (
    :prompt_id,
    :bot_class,
    :walltime_seconds,
    :request_count,
    :token_count,
    :pending_question);
