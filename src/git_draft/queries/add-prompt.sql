insert into prompts (folio_id, template, contents)
  values (:folio_id, :template, :contents)
  returning id;
