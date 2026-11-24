-- Project managers can read the volunteer pages. They cannot claim, annotate, or edit.

ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'project_manager';

CREATE OR REPLACE FUNCTION is_project_manager()
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
      AND role::text = 'project_manager'
      AND is_active
  );
$$;

REVOKE ALL ON FUNCTION is_project_manager() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION is_project_manager() TO authenticated;

-- Read the rows the Workspace list and Dashboard already query.
CREATE POLICY profiles_pm_select ON profiles
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY datasets_pm_select ON datasets
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY segments_pm_select ON segments
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY error_candidates_pm_select ON error_candidates
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY batch_items_pm_select ON batch_items
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY bic_pm_select ON batch_item_candidates
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY annotations_pm_select ON annotations
  FOR SELECT TO authenticated
  USING (is_project_manager());

CREATE POLICY error_suggestions_pm_select ON error_suggestions
  FOR SELECT TO authenticated
  USING (is_project_manager());

DROP POLICY IF EXISTS annotations_insert ON annotations;
CREATE POLICY annotations_insert ON annotations
  FOR INSERT TO authenticated
  WITH CHECK (
    annotator_id = auth.uid()
    AND is_active_user()
    AND NOT is_project_manager()
  );

DROP POLICY IF EXISTS annotations_update ON annotations;
CREATE POLICY annotations_update ON annotations
  FOR UPDATE TO authenticated
  USING (annotator_id = auth.uid() AND NOT is_project_manager())
  WITH CHECK (annotator_id = auth.uid() AND NOT is_project_manager());

DROP POLICY IF EXISTS error_suggestions_insert ON error_suggestions;
CREATE POLICY error_suggestions_insert ON error_suggestions
  FOR INSERT TO authenticated
  WITH CHECK (
    author_id = auth.uid()
    AND is_active_user()
    AND NOT is_project_manager()
  );

CREATE OR REPLACE FUNCTION reject_project_manager_write()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF is_project_manager() THEN
    RAISE EXCEPTION 'Project managers cannot change this data';
  END IF;
  RETURN COALESCE(NEW, OLD);
END;
$$;

DROP TRIGGER IF EXISTS trg_batches_no_pm ON batches;
CREATE TRIGGER trg_batches_no_pm
  BEFORE INSERT OR UPDATE OR DELETE ON batches
  FOR EACH ROW EXECUTE FUNCTION reject_project_manager_write();

DROP TRIGGER IF EXISTS trg_annotations_no_pm ON annotations;
CREATE TRIGGER trg_annotations_no_pm
  BEFORE INSERT OR UPDATE OR DELETE ON annotations
  FOR EACH ROW EXECUTE FUNCTION reject_project_manager_write();

DROP TRIGGER IF EXISTS trg_error_suggestions_no_pm ON error_suggestions;
CREATE TRIGGER trg_error_suggestions_no_pm
  BEFORE INSERT OR UPDATE OR DELETE ON error_suggestions
  FOR EACH ROW EXECUTE FUNCTION reject_project_manager_write();
