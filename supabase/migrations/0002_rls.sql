-- Row Level Security. Authorization lives here, not in the UI.

CREATE OR REPLACE FUNCTION is_admin()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM profiles
    WHERE id = auth.uid()
      AND role = 'admin'
      AND is_active
  );
$$;

CREATE OR REPLACE FUNCTION is_active_user()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM profiles
    WHERE id = auth.uid()
      AND is_active
  );
$$;

REVOKE ALL ON FUNCTION is_admin() FROM PUBLIC;
REVOKE ALL ON FUNCTION is_active_user() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION is_admin() TO authenticated;
GRANT EXECUTE ON FUNCTION is_active_user() TO authenticated;

ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE language_pairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE segments ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE batches ENABLE ROW LEVEL SECURITY;
ALTER TABLE batch_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE batch_item_candidates ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;
ALTER TABLE annotation_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE error_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_audit_log ENABLE ROW LEVEL SECURITY;

-- Force RLS so the table owner is also subject when SET ROLE authenticated.
ALTER TABLE profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE language_pairs FORCE ROW LEVEL SECURITY;
ALTER TABLE datasets FORCE ROW LEVEL SECURITY;
ALTER TABLE segments FORCE ROW LEVEL SECURITY;
ALTER TABLE error_candidates FORCE ROW LEVEL SECURITY;
ALTER TABLE batches FORCE ROW LEVEL SECURITY;
ALTER TABLE batch_items FORCE ROW LEVEL SECURITY;
ALTER TABLE batch_item_candidates FORCE ROW LEVEL SECURITY;
ALTER TABLE annotations FORCE ROW LEVEL SECURITY;
ALTER TABLE annotation_history FORCE ROW LEVEL SECURITY;
ALTER TABLE error_suggestions FORCE ROW LEVEL SECURITY;
ALTER TABLE admin_audit_log FORCE ROW LEVEL SECURITY;

-- profiles -----------------------------------------------------------------
CREATE POLICY profiles_select ON profiles
  FOR SELECT TO authenticated
  USING (id = auth.uid() OR is_admin());

CREATE POLICY profiles_update_self ON profiles
  FOR UPDATE TO authenticated
  USING (id = auth.uid())
  WITH CHECK (id = auth.uid() AND role = (SELECT p.role FROM profiles p WHERE p.id = auth.uid()));

CREATE POLICY profiles_admin_write ON profiles
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- language pairs ------------------------------------------------------------
CREATE POLICY language_pairs_select ON language_pairs
  FOR SELECT TO authenticated
  USING (is_active_user());

CREATE POLICY language_pairs_admin ON language_pairs
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- datasets ------------------------------------------------------------------
CREATE POLICY datasets_select ON datasets
  FOR SELECT TO authenticated
  USING (
    is_admin()
    OR EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      JOIN segments s ON s.id = bi.segment_id
      WHERE s.dataset_id = datasets.id
        AND b.owner_id = auth.uid()
    )
  );

CREATE POLICY datasets_admin ON datasets
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- segments ------------------------------------------------------------------
CREATE POLICY segments_select ON segments
  FOR SELECT TO authenticated
  USING (
    is_admin()
    OR EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.segment_id = segments.id
        AND b.owner_id = auth.uid()
    )
  );

CREATE POLICY segments_admin ON segments
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- error_candidates ----------------------------------------------------------
CREATE POLICY error_candidates_select ON error_candidates
  FOR SELECT TO authenticated
  USING (
    is_admin()
    OR EXISTS (
      SELECT 1
      FROM batch_item_candidates bic
      JOIN batch_items bi ON bi.id = bic.batch_item_id
      JOIN batches b ON b.id = bi.batch_id
      WHERE bic.candidate_id = error_candidates.id
        AND b.owner_id = auth.uid()
    )
  );

CREATE POLICY error_candidates_admin ON error_candidates
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- batches: metadata is visible so volunteers can see status + owner names.
-- Item contents remain restricted below.
CREATE POLICY batches_select ON batches
  FOR SELECT TO authenticated
  USING (is_active_user());

CREATE POLICY batches_admin ON batches
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- batch_items ---------------------------------------------------------------
CREATE POLICY batch_items_select ON batch_items
  FOR SELECT TO authenticated
  USING (
    is_admin()
    OR EXISTS (
      SELECT 1 FROM batches b
      WHERE b.id = batch_items.batch_id AND b.owner_id = auth.uid()
    )
  );

CREATE POLICY batch_items_admin ON batch_items
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- batch_item_candidates -----------------------------------------------------
CREATE POLICY bic_select ON batch_item_candidates
  FOR SELECT TO authenticated
  USING (
    is_admin()
    OR EXISTS (
      SELECT 1
      FROM batch_items bi
      JOIN batches b ON b.id = bi.batch_id
      WHERE bi.id = batch_item_candidates.batch_item_id
        AND b.owner_id = auth.uid()
    )
  );

CREATE POLICY bic_admin ON batch_item_candidates
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- annotations: IAA blindness — translators never read others' judgments -----
CREATE POLICY annotations_select ON annotations
  FOR SELECT TO authenticated
  USING (annotator_id = auth.uid() OR is_admin());

CREATE POLICY annotations_insert ON annotations
  FOR INSERT TO authenticated
  WITH CHECK (annotator_id = auth.uid() AND is_active_user());

CREATE POLICY annotations_update ON annotations
  FOR UPDATE TO authenticated
  USING (annotator_id = auth.uid())
  WITH CHECK (annotator_id = auth.uid());

CREATE POLICY annotations_admin ON annotations
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- annotation_history --------------------------------------------------------
CREATE POLICY annotation_history_select ON annotation_history
  FOR SELECT TO authenticated
  USING (
    is_admin()
    OR EXISTS (
      SELECT 1 FROM annotations a
      WHERE a.id = annotation_history.annotation_id
        AND a.annotator_id = auth.uid()
    )
  );

CREATE POLICY annotation_history_admin ON annotation_history
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- error_suggestions ---------------------------------------------------------
CREATE POLICY error_suggestions_select ON error_suggestions
  FOR SELECT TO authenticated
  USING (author_id = auth.uid() OR is_admin());

CREATE POLICY error_suggestions_insert ON error_suggestions
  FOR INSERT TO authenticated
  WITH CHECK (author_id = auth.uid() AND is_active_user());

CREATE POLICY error_suggestions_admin ON error_suggestions
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- admin_audit_log -----------------------------------------------------------
CREATE POLICY admin_audit_log_admin ON admin_audit_log
  FOR ALL TO authenticated
  USING (is_admin())
  WITH CHECK (is_admin());

-- Grants -------------------------------------------------------------------
GRANT USAGE ON SCHEMA public TO authenticated, anon;

GRANT SELECT ON profiles_public TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  profiles,
  language_pairs,
  datasets,
  segments,
  error_candidates,
  batches,
  batch_items,
  batch_item_candidates,
  annotations,
  annotation_history,
  error_suggestions,
  admin_audit_log
TO authenticated;

GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;
