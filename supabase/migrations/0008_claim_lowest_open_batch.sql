-- Claim the lowest free batch number. A released batch is deleted, so its
-- number can be claimed again even when a later batch still exists.

CREATE OR REPLACE FUNCTION next_open_batch_number(p_language_pair_id uuid)
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT min(candidate)
  FROM generate_series(
    1,
    coalesce((SELECT max(batch_number) FROM batches WHERE language_pair_id = p_language_pair_id), 0) + 1
  ) AS candidate
  WHERE NOT EXISTS (
    SELECT 1
    FROM batches b
    WHERE b.language_pair_id = p_language_pair_id
      AND b.batch_number = candidate
  );
$$;

GRANT EXECUTE ON FUNCTION next_open_batch_number(uuid) TO authenticated;

CREATE OR REPLACE FUNCTION claim_batch(p_language_pair_id uuid)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid uuid := auth.uid();
  v_batch_size integer;
  v_iaa_pct numeric;
  v_total integer;
  v_iaa_target integer;
  v_iaa_have integer;
  v_overlap_budget integer;
  v_batch_id uuid;
  v_batch_number integer;
  v_pos integer := 0;
  v_item_id uuid;
  r record;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;
  IF NOT is_active_user() THEN
    RAISE EXCEPTION 'Account is not active';
  END IF;

  PERFORM _lock_language_pair(p_language_pair_id);

  IF EXISTS (SELECT 1 FROM batches WHERE owner_id = v_uid AND status = 'active') THEN
    RAISE EXCEPTION 'You already have an active batch';
  END IF;

  -- Language assignment is enforced only here. Batch rows stay visible to
  -- every active user; this blocks claiming a pair the caller was not given.
  IF NOT EXISTS (
    SELECT 1
    FROM translator_languages
    WHERE profile_id = v_uid
      AND language_pair_id = p_language_pair_id
  ) THEN
    RAISE EXCEPTION 'You are not assigned this language pair';
  END IF;

  SELECT lp.batch_size, lp.iaa_target_pct
    INTO v_batch_size, v_iaa_pct
  FROM language_pairs lp
  WHERE lp.id = p_language_pair_id AND lp.is_active;
  IF v_batch_size IS NULL THEN
    RAISE EXCEPTION 'Language pair not found or inactive';
  END IF;

  SELECT count(DISTINCT s.id) INTO v_total
  FROM segments s
  JOIN datasets d ON d.id = s.dataset_id
  WHERE d.language_pair_id = p_language_pair_id
    AND d.status = 'published'
    AND EXISTS (
      SELECT 1 FROM error_candidates c
      WHERE c.segment_id = s.id AND c.status = 'published'
    );
  IF v_total = 0 THEN
    RAISE EXCEPTION 'No published segments for this language pair';
  END IF;

  v_iaa_target := ceil(v_total * v_iaa_pct / 100.0);

  SELECT count(*) INTO v_iaa_have
  FROM (
    SELECT sc.segment_id
    FROM segment_completion sc
    WHERE sc.language_pair_id = p_language_pair_id AND sc.is_complete
    GROUP BY sc.segment_id
    HAVING count(DISTINCT sc.annotator_id) >= 2
  ) x;

  v_overlap_budget := greatest(v_iaa_target - v_iaa_have, 0);

  DROP TABLE IF EXISTS _claim_pick;
  CREATE TEMP TABLE _claim_pick (
    segment_id uuid PRIMARY KEY,
    kind text NOT NULL,
    sample_order integer NOT NULL
  );

  -- 1. Overlap: segments completed by exactly one other translator.
  INSERT INTO _claim_pick (segment_id, kind, sample_order)
  SELECT s.id, 'overlap', s.sample_order
  FROM segments s
  JOIN datasets d ON d.id = s.dataset_id
  WHERE d.language_pair_id = p_language_pair_id
    AND d.status = 'published'
    AND EXISTS (
      SELECT 1
      FROM segment_completion sc
      WHERE sc.segment_id = s.id AND sc.is_complete
      GROUP BY sc.segment_id
      HAVING count(DISTINCT sc.annotator_id) = 1
         AND bool_and(sc.annotator_id <> v_uid)
    )
    AND NOT EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.segment_id = s.id AND b.owner_id = v_uid
    )
  ORDER BY s.sample_order
  LIMIT v_overlap_budget;

  -- 2. Fresh never-assigned segments.
  INSERT INTO _claim_pick (segment_id, kind, sample_order)
  SELECT s.id, 'fresh', s.sample_order
  FROM segments s
  JOIN datasets d ON d.id = s.dataset_id
  WHERE d.language_pair_id = p_language_pair_id
    AND d.status = 'published'
    AND EXISTS (
      SELECT 1 FROM error_candidates c
      WHERE c.segment_id = s.id AND c.status = 'published'
    )
    AND NOT EXISTS (SELECT 1 FROM batch_items bi WHERE bi.segment_id = s.id)
    AND NOT EXISTS (SELECT 1 FROM _claim_pick p WHERE p.segment_id = s.id)
  ORDER BY s.sample_order
  LIMIT greatest(v_batch_size - (SELECT count(*) FROM _claim_pick), 0);

  -- 3. If still short of overlap budget, take once-assigned in-progress segments.
  INSERT INTO _claim_pick (segment_id, kind, sample_order)
  SELECT s.id, 'overlap', s.sample_order
  FROM segments s
  JOIN datasets d ON d.id = s.dataset_id
  WHERE d.language_pair_id = p_language_pair_id
    AND d.status = 'published'
    AND EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.segment_id = s.id
      GROUP BY bi.segment_id
      HAVING count(DISTINCT b.owner_id) = 1
         AND bool_and(b.owner_id <> v_uid)
    )
    AND NOT EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.segment_id = s.id AND b.owner_id = v_uid
    )
    AND NOT EXISTS (SELECT 1 FROM _claim_pick p WHERE p.segment_id = s.id)
  ORDER BY s.sample_order
  LIMIT greatest(
    least(
      v_overlap_budget - (SELECT count(*) FROM _claim_pick WHERE kind = 'overlap'),
      v_batch_size - (SELECT count(*) FROM _claim_pick)
    ),
    0
  );

  IF (SELECT count(*) FROM _claim_pick) = 0 THEN
    RAISE EXCEPTION 'No eligible segments available to claim for this language pair';
  END IF;

  v_batch_number := next_open_batch_number(p_language_pair_id);

  INSERT INTO batches (language_pair_id, owner_id, batch_number, status, last_position)
  VALUES (p_language_pair_id, v_uid, v_batch_number, 'active', 1)
  RETURNING id INTO v_batch_id;

  FOR r IN
    SELECT segment_id, kind FROM _claim_pick ORDER BY sample_order, segment_id
  LOOP
    v_pos := v_pos + 1;
    INSERT INTO batch_items (batch_id, segment_id, position)
    VALUES (v_batch_id, r.segment_id, v_pos)
    RETURNING id INTO v_item_id;

    IF r.kind = 'overlap' THEN
      INSERT INTO batch_item_candidates (batch_item_id, candidate_id)
      SELECT v_item_id, bic.candidate_id
      FROM batch_item_candidates bic
      JOIN batch_items bi ON bi.id = bic.batch_item_id
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.segment_id = r.segment_id
        AND bi.id = (
          SELECT bi2.id
          FROM batch_items bi2
          JOIN batches b2 ON b2.id = bi2.batch_id
          WHERE bi2.segment_id = r.segment_id
          ORDER BY b2.claimed_at, bi2.id
          LIMIT 1
        );
    ELSE
      INSERT INTO batch_item_candidates (batch_item_id, candidate_id)
      SELECT v_item_id, x.id
      FROM (
        SELECT DISTINCT ON (c.external_id) c.id
        FROM error_candidates c
        WHERE c.segment_id = r.segment_id AND c.status = 'published'
        ORDER BY c.external_id, c.version DESC
      ) x;
    END IF;
  END LOOP;

  INSERT INTO admin_audit_log (actor_id, action, entity, entity_id, details)
  VALUES (
    v_uid,
    'claim_batch',
    'batches',
    v_batch_id,
    jsonb_build_object(
      'language_pair_id', p_language_pair_id,
      'size', v_pos,
      'overlap_budget', v_overlap_budget
    )
  );

  RETURN v_batch_id;
END;
$$;

GRANT EXECUTE ON FUNCTION claim_batch(uuid) TO authenticated;
