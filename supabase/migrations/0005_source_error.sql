-- Flag that the source or reference already contains an error.

ALTER TABLE batch_items
  ADD COLUMN IF NOT EXISTS source_error boolean NOT NULL DEFAULT false;

CREATE OR REPLACE FUNCTION flag_source_error(
  p_batch_id uuid,
  p_segment_id uuid,
  p_flagged boolean
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF auth.uid() IS NULL OR NOT is_active_user() THEN
    RAISE EXCEPTION 'Not authenticated';
  END IF;
  UPDATE batch_items bi
  SET source_error = coalesce(p_flagged, false)
  FROM batches b
  WHERE bi.batch_id = b.id
    AND bi.batch_id = p_batch_id
    AND bi.segment_id = p_segment_id
    AND (b.owner_id = auth.uid() OR is_admin());
  IF NOT FOUND THEN
    RAISE EXCEPTION 'Segment is not in your batch';
  END IF;
END;
$$;

GRANT EXECUTE ON FUNCTION flag_source_error(uuid, uuid, boolean) TO authenticated;
