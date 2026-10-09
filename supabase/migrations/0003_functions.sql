-- RPCs: batch allocation, annotation saves, IAA views, admin helpers.

-- Completion of a segment for a given annotator: every pinned candidate is
-- validated or rejected.
CREATE OR REPLACE VIEW segment_completion AS
SELECT
  bi.id AS batch_item_id,
  bi.segment_id,
  b.owner_id AS annotator_id,
  b.language_pair_id,
  b.id AS batch_id,
  count(bic.candidate_id) AS n_candidates,
  count(a.id) FILTER (WHERE a.status IN ('validated', 'rejected')) AS n_resolved,
  (
    count(bic.candidate_id) > 0
    AND count(a.id) FILTER (WHERE a.status IN ('validated', 'rejected'))
        = count(bic.candidate_id)
  ) AS is_complete
FROM batch_items bi
JOIN batches b ON b.id = bi.batch_id
JOIN batch_item_candidates bic ON bic.batch_item_id = bi.id
LEFT JOIN annotations a
  ON a.candidate_id = bic.candidate_id
 AND a.annotator_id = b.owner_id
GROUP BY bi.id, bi.segment_id, b.owner_id, b.language_pair_id, b.id;

ALTER VIEW segment_completion SET (security_invoker = true);
GRANT SELECT ON segment_completion TO authenticated;

CREATE OR REPLACE VIEW iaa_pair_stats AS
WITH published_segments AS (
  SELECT DISTINCT s.id AS segment_id, d.language_pair_id
  FROM segments s
  JOIN datasets d ON d.id = s.dataset_id
  WHERE d.status = 'published'
    AND EXISTS (
      SELECT 1 FROM error_candidates c
      WHERE c.segment_id = s.id AND c.status = 'published'
    )
),
completed AS (
  SELECT language_pair_id, segment_id, count(DISTINCT annotator_id) AS n_annotators
  FROM segment_completion
  WHERE is_complete
  GROUP BY language_pair_id, segment_id
)
SELECT
  lp.id AS language_pair_id,
  lp.source_lang,
  lp.target_lang,
  lp.iaa_target_pct,
  (SELECT count(*) FROM published_segments ps WHERE ps.language_pair_id = lp.id) AS unique_segments,
  (SELECT count(*) FROM completed c WHERE c.language_pair_id = lp.id AND c.n_annotators >= 1) AS unique_with_one,
  (SELECT count(*) FROM completed c WHERE c.language_pair_id = lp.id AND c.n_annotators >= 2) AS unique_with_two,
  CASE
    WHEN (SELECT count(*) FROM published_segments ps WHERE ps.language_pair_id = lp.id) = 0 THEN 0
    ELSE round(
      100.0 * (SELECT count(*) FROM completed c WHERE c.language_pair_id = lp.id AND c.n_annotators >= 2)
      / (SELECT count(*) FROM published_segments ps WHERE ps.language_pair_id = lp.id)
    , 2)
  END AS coverage_pct,
  ceil(
    coalesce((SELECT count(*) FROM published_segments ps WHERE ps.language_pair_id = lp.id), 0)
    * lp.iaa_target_pct / 100.0
  )::integer AS iaa_target_count
FROM language_pairs lp;

GRANT SELECT ON iaa_pair_stats TO authenticated;

-- Pairwise agreement on overlapping completed segments (admin-oriented).
CREATE OR REPLACE VIEW iaa_agreements AS
WITH pairs AS (
  SELECT
    a.segment_id,
    a.language_pair_id,
    a.annotator_id AS annotator_a,
    b.annotator_id AS annotator_b
  FROM segment_completion a
  JOIN segment_completion b
    ON a.segment_id = b.segment_id
   AND a.annotator_id < b.annotator_id
   AND a.is_complete AND b.is_complete
),
cand AS (
  SELECT
    p.segment_id,
    p.language_pair_id,
    p.annotator_a,
    p.annotator_b,
    bic.candidate_id,
    aa.status AS status_a,
    ab.status AS status_b,
    aa.error_type AS type_a,
    ab.error_type AS type_b,
    aa.severity AS sev_a,
    ab.severity AS sev_b
  FROM pairs p
  JOIN batch_items bi ON bi.segment_id = p.segment_id
  JOIN batch_item_candidates bic ON bic.batch_item_id = bi.id
  JOIN annotations aa ON aa.candidate_id = bic.candidate_id AND aa.annotator_id = p.annotator_a
  JOIN annotations ab ON ab.candidate_id = bic.candidate_id AND ab.annotator_id = p.annotator_b
)
SELECT
  language_pair_id,
  segment_id,
  candidate_id,
  annotator_a,
  annotator_b,
  status_a,
  status_b,
  (status_a = status_b) AS status_agree,
  type_a,
  type_b,
  sev_a,
  sev_b,
  (status_a = 'validated' AND status_b = 'validated' AND type_a = type_b) AS type_agree,
  (status_a = 'validated' AND status_b = 'validated' AND sev_a = sev_b) AS severity_agree
FROM cand;

ALTER VIEW iaa_agreements SET (security_invoker = true);
GRANT SELECT ON iaa_agreements TO authenticated;

-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION _lock_language_pair(p_language_pair_id uuid)
RETURNS void
LANGUAGE sql
AS $$
  SELECT pg_advisory_xact_lock(
    ('x' || substr(md5(p_language_pair_id::text), 1, 16))::bit(64)::bigint
  );
$$;

CREATE OR REPLACE FUNCTION claimable_count(p_language_pair_id uuid)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid uuid := auth.uid();
  v_iaa_pct numeric;
  v_total integer;
  v_iaa_target integer;
  v_iaa_have integer;
  v_overlap_budget integer;
  v_fresh integer;
  v_overlap integer;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;

  SELECT lp.iaa_target_pct INTO v_iaa_pct
  FROM language_pairs lp
  WHERE lp.id = p_language_pair_id AND lp.is_active;
  IF v_iaa_pct IS NULL THEN
    RETURN 0;
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

  SELECT count(*) INTO v_fresh
  FROM segments s
  JOIN datasets d ON d.id = s.dataset_id
  WHERE d.language_pair_id = p_language_pair_id
    AND d.status = 'published'
    AND EXISTS (
      SELECT 1 FROM error_candidates c
      WHERE c.segment_id = s.id AND c.status = 'published'
    )
    AND NOT EXISTS (SELECT 1 FROM batch_items bi WHERE bi.segment_id = s.id)
    AND NOT EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.segment_id = s.id AND b.owner_id = v_uid
    );

  SELECT count(*) INTO v_overlap
  FROM (
    SELECT sc.segment_id
    FROM segment_completion sc
    WHERE sc.language_pair_id = p_language_pair_id
    GROUP BY sc.segment_id
    HAVING count(DISTINCT sc.annotator_id) = 1
       AND count(DISTINCT sc.annotator_id) FILTER (WHERE sc.annotator_id = v_uid) = 0
  ) x;

  RETURN (v_fresh + least(v_overlap, v_overlap_budget))::integer;
END;
$$;

GRANT EXECUTE ON FUNCTION claimable_count(uuid) TO authenticated;

-- ---------------------------------------------------------------------------
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

  SELECT coalesce(max(batch_number), 0) + 1 INTO v_batch_number
  FROM batches
  WHERE language_pair_id = p_language_pair_id;

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

-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION save_annotation(
  p_candidate_id uuid,
  p_batch_id uuid,
  p_status text,
  p_edited_text text,
  p_error_type text,
  p_severity text,
  p_rejection_reason text,
  p_comment text,
  p_expected_version integer
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid uuid := auth.uid();
  v_row annotations%ROWTYPE;
  v_reason rejection_reason;
  v_all_resolved boolean;
BEGIN
  IF v_uid IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;
  IF NOT is_active_user() THEN
    RAISE EXCEPTION 'Account is not active';
  END IF;
  IF p_status NOT IN ('draft', 'validated', 'rejected') THEN
    RAISE EXCEPTION 'Invalid status';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM batch_item_candidates bic
    JOIN batch_items bi ON bi.id = bic.batch_item_id
    JOIN batches b ON b.id = bi.batch_id
    WHERE bic.candidate_id = p_candidate_id
      AND bi.batch_id = p_batch_id
      AND b.owner_id = v_uid
  ) THEN
    RAISE EXCEPTION 'Candidate is not in your batch';
  END IF;

  IF p_status = 'rejected' THEN
    IF p_rejection_reason IS NULL OR p_rejection_reason = '' THEN
      RAISE EXCEPTION 'Rejection reason is required';
    END IF;
    v_reason := p_rejection_reason::rejection_reason;
  ELSE
    v_reason := NULL;
  END IF;

  SELECT * INTO v_row
  FROM annotations
  WHERE candidate_id = p_candidate_id AND annotator_id = v_uid;

  IF NOT FOUND THEN
    IF coalesce(p_expected_version, 0) <> 0 THEN
      RAISE EXCEPTION 'version_conflict' USING ERRCODE = '40001';
    END IF;
    INSERT INTO annotations (
      candidate_id, annotator_id, batch_id, status, edited_text,
      error_type, severity, rejection_reason, comment, version
    ) VALUES (
      p_candidate_id, v_uid, p_batch_id, p_status::annotation_status, p_edited_text,
      p_error_type::error_type, p_severity::severity, v_reason, p_comment, 1
    ) RETURNING * INTO v_row;
  ELSE
    IF v_row.version IS DISTINCT FROM p_expected_version THEN
      RAISE EXCEPTION 'version_conflict' USING ERRCODE = '40001';
    END IF;
    UPDATE annotations SET
      status = p_status::annotation_status,
      edited_text = p_edited_text,
      error_type = p_error_type::error_type,
      severity = p_severity::severity,
      rejection_reason = v_reason,
      comment = p_comment,
      version = annotations.version + 1,
      batch_id = p_batch_id
    WHERE id = v_row.id AND version = p_expected_version
    RETURNING * INTO v_row;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'version_conflict' USING ERRCODE = '40001';
    END IF;
  END IF;

  INSERT INTO annotation_history (annotation_id, rev, snapshot)
  VALUES (v_row.id, v_row.version, to_jsonb(v_row));

  -- Auto-complete the batch when every pinned candidate is resolved.
  SELECT
    count(bic.candidate_id) > 0
    AND count(a.id) FILTER (WHERE a.status IN ('validated', 'rejected')) = count(bic.candidate_id)
  INTO v_all_resolved
  FROM batch_items bi
  JOIN batch_item_candidates bic ON bic.batch_item_id = bi.id
  LEFT JOIN annotations a
    ON a.candidate_id = bic.candidate_id AND a.annotator_id = v_uid
  WHERE bi.batch_id = p_batch_id;

  IF v_all_resolved THEN
    UPDATE batches
    SET status = 'completed', completed_at = now()
    WHERE id = p_batch_id AND owner_id = v_uid AND status = 'active';
  ELSE
    UPDATE batches
    SET status = 'active', completed_at = NULL
    WHERE id = p_batch_id AND owner_id = v_uid AND status = 'completed';
  END IF;

  RETURN to_jsonb(v_row);
END;
$$;

GRANT EXECUTE ON FUNCTION save_annotation(uuid, uuid, text, text, text, text, text, text, integer) TO authenticated;

-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_batch_position(p_batch_id uuid, p_position integer)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NULL THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;
  UPDATE batches
  SET last_position = greatest(p_position, 1)
  WHERE id = p_batch_id AND owner_id = auth.uid();
  IF NOT FOUND AND NOT is_admin() THEN
    RAISE EXCEPTION 'Batch not found';
  END IF;
  IF NOT FOUND AND is_admin() THEN
    UPDATE batches SET last_position = greatest(p_position, 1) WHERE id = p_batch_id;
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION set_batch_position(uuid, integer) TO authenticated;

CREATE OR REPLACE FUNCTION submit_error_suggestion(
  p_segment_id uuid,
  p_batch_id uuid,
  p_suggested_text text,
  p_error_type text,
  p_severity text,
  p_notes text
) RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_uid uuid := auth.uid();
  v_id uuid;
BEGIN
  IF v_uid IS NULL OR NOT is_active_user() THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM batch_items bi
    JOIN batches b ON b.id = bi.batch_id
    WHERE bi.batch_id = p_batch_id AND bi.segment_id = p_segment_id AND b.owner_id = v_uid
  ) THEN
    RAISE EXCEPTION 'Segment is not in your batch';
  END IF;
  INSERT INTO error_suggestions (
    segment_id, batch_id, author_id, suggested_text, error_type, severity, notes
  ) VALUES (
    p_segment_id, p_batch_id, v_uid, p_suggested_text,
    p_error_type::error_type, p_severity::severity, p_notes
  ) RETURNING id INTO v_id;
  RETURN v_id;
END;
$$;

GRANT EXECUTE ON FUNCTION submit_error_suggestion(uuid, uuid, text, text, text, text) TO authenticated;

-- ---------------------------------------------------------------------------
-- Admin helpers
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION release_batch(p_batch_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT is_admin() THEN
    RAISE EXCEPTION 'Admin required';
  END IF;
  UPDATE batches
  SET status = 'released', released_at = now()
  WHERE id = p_batch_id AND status = 'active';
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Active batch not found';
  END IF;
  INSERT INTO admin_audit_log (actor_id, action, entity, entity_id, details)
  VALUES (auth.uid(), 'release_batch', 'batches', p_batch_id, '{}'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION release_batch(uuid) TO authenticated;

CREATE OR REPLACE FUNCTION reassign_batch(p_batch_id uuid, p_new_owner uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_pair uuid;
BEGIN
  IF NOT is_admin() THEN
    RAISE EXCEPTION 'Admin required';
  END IF;
  IF EXISTS (SELECT 1 FROM batches WHERE owner_id = p_new_owner AND status = 'active') THEN
    RAISE EXCEPTION 'Target translator already has an active batch';
  END IF;
  SELECT language_pair_id INTO v_pair FROM batches WHERE id = p_batch_id;
  IF v_pair IS NULL THEN
    RAISE EXCEPTION 'Batch not found';
  END IF;
  -- Reassignment cannot give the new owner a segment they already had.
  IF EXISTS (
    SELECT 1
    FROM batch_items bi
    JOIN batch_items bi2 ON bi2.segment_id = bi.segment_id
    JOIN batches b2 ON b2.id = bi2.batch_id
    WHERE bi.batch_id = p_batch_id
      AND b2.owner_id = p_new_owner
      AND b2.id <> p_batch_id
  ) THEN
    RAISE EXCEPTION 'Target translator was already assigned one or more of these segments';
  END IF;
  UPDATE batches
  SET owner_id = p_new_owner, status = 'active', released_at = NULL, completed_at = NULL
  WHERE id = p_batch_id;
  INSERT INTO admin_audit_log (actor_id, action, entity, entity_id, details)
  VALUES (
    auth.uid(), 'reassign_batch', 'batches', p_batch_id,
    jsonb_build_object('new_owner', p_new_owner)
  );
END;
$$;

GRANT EXECUTE ON FUNCTION reassign_batch(uuid, uuid) TO authenticated;

CREATE OR REPLACE FUNCTION write_audit(
  p_action text,
  p_entity text,
  p_entity_id uuid,
  p_details jsonb
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT is_admin() THEN
    RAISE EXCEPTION 'Admin required';
  END IF;
  INSERT INTO admin_audit_log (actor_id, action, entity, entity_id, details)
  VALUES (auth.uid(), p_action, p_entity, p_entity_id, coalesce(p_details, '{}'::jsonb));
END;
$$;

GRANT EXECUTE ON FUNCTION write_audit(text, text, uuid, jsonb) TO authenticated;
