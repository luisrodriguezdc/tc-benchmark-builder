-- Seed the English → Spanish pair. Other pairs are added by admins.
-- Only pairs with published data appear as claimable in the UI.

INSERT INTO language_pairs (
  source_lang, target_lang, source_label, target_label, iaa_target_pct, batch_size, is_active
) VALUES (
  'en', 'es-ES', 'English', 'Spanish', 15, 100, true
)
ON CONFLICT (source_lang, target_lang) DO NOTHING;
