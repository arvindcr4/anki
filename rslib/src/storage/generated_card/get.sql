SELECT id,
  front,
  back,
  source_url,
  source_type,
  created_at,
  sync_status,
  tags,
  is_cloze
FROM generated_cards
WHERE id = ?