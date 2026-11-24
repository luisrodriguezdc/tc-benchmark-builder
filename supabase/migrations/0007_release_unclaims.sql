-- Releasing a batch returns it to the unclaimed slot.
-- Annotations from that claim are removed. Segments and imported candidates stay.

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
  IF NOT EXISTS (
    SELECT 1 FROM batches
    WHERE id = p_batch_id AND status IN ('active', 'released')
  ) THEN
    RAISE EXCEPTION 'Active batch not found';
  END IF;

  DELETE FROM annotation_history
  WHERE annotation_id IN (
    SELECT id FROM annotations WHERE batch_id = p_batch_id
  );
  DELETE FROM annotations WHERE batch_id = p_batch_id;
  DELETE FROM error_suggestions WHERE batch_id = p_batch_id;
  -- batch_items and batch_item_candidates cascade from the batch row.
  DELETE FROM batches WHERE id = p_batch_id;

  INSERT INTO admin_audit_log (actor_id, action, entity, entity_id, details)
  VALUES (auth.uid(), 'release_batch', 'batches', p_batch_id, '{}'::jsonb);
END;
$$;

GRANT EXECUTE ON FUNCTION release_batch(uuid) TO authenticated;
