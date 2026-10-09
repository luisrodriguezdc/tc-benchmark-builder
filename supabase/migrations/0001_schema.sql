-- Translation Commons Benchmark Builder — schema
-- Assumes gen_random_uuid() is available (pgcrypto / pg 13+).

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TYPE user_role AS ENUM ('translator', 'admin');
CREATE TYPE dataset_status AS ENUM ('draft', 'published', 'archived');
CREATE TYPE candidate_status AS ENUM ('draft', 'published', 'archived');
CREATE TYPE batch_status AS ENUM ('active', 'completed', 'released');
CREATE TYPE annotation_status AS ENUM ('draft', 'validated', 'rejected');
CREATE TYPE error_type AS ENUM ('Mistranslation', 'Addition', 'Omission');
CREATE TYPE severity AS ENUM ('Minor', 'Major');
CREATE TYPE rejection_reason AS ENUM (
  'no_meaningful_error',
  'multiple_errors',
  'grammar_fluency_plausibility',
  'incorrect_unclear_perturbation',
  'other'
);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

-- ---------------------------------------------------------------------------
-- Users
-- ---------------------------------------------------------------------------

CREATE TABLE profiles (
  id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  email text NOT NULL UNIQUE,
  display_name text NOT NULL DEFAULT '',
  role user_role NOT NULL DEFAULT 'translator',
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER trg_profiles_updated_at
  BEFORE UPDATE ON profiles
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Display names only — never emails — for volunteer-facing owner columns.
CREATE VIEW profiles_public AS
SELECT id, display_name, role, is_active
FROM profiles;

-- ---------------------------------------------------------------------------
-- Language pairs and datasets
-- ---------------------------------------------------------------------------

CREATE TABLE language_pairs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_lang text NOT NULL,
  target_lang text NOT NULL,
  source_label text NOT NULL DEFAULT '',
  target_label text NOT NULL DEFAULT '',
  iaa_target_pct numeric(5, 2) NOT NULL DEFAULT 15
    CHECK (iaa_target_pct >= 0 AND iaa_target_pct <= 100),
  batch_size integer NOT NULL DEFAULT 100 CHECK (batch_size > 0),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (source_lang, target_lang)
);

CREATE TRIGGER trg_language_pairs_updated_at
  BEFORE UPDATE ON language_pairs
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE datasets (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  language_pair_id uuid NOT NULL REFERENCES language_pairs (id),
  name text NOT NULL,
  version text NOT NULL DEFAULT '1',
  status dataset_status NOT NULL DEFAULT 'draft',
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (language_pair_id, name, version)
);

CREATE TRIGGER trg_datasets_updated_at
  BEFORE UPDATE ON datasets
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE segments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  dataset_id uuid NOT NULL REFERENCES datasets (id) ON DELETE CASCADE,
  external_id text NOT NULL,
  source_text text NOT NULL,
  reference_text text NOT NULL,
  sample_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (dataset_id, external_id)
);

CREATE INDEX idx_segments_dataset ON segments (dataset_id);
CREATE INDEX idx_segments_order ON segments (dataset_id, sample_order);

CREATE TRIGGER trg_segments_updated_at
  BEFORE UPDATE ON segments
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE error_candidates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id uuid NOT NULL REFERENCES segments (id) ON DELETE CASCADE,
  external_id text NOT NULL,
  version integer NOT NULL DEFAULT 1,
  status candidate_status NOT NULL DEFAULT 'draft',
  error_type error_type NOT NULL,
  severity severity NOT NULL,
  generated_text text NOT NULL,
  target_span_start integer,
  target_span_end integer,
  ref_span_start integer,
  ref_span_end integer,
  target_insert_pos integer,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (segment_id, external_id, version),
  CHECK (
    target_span_start IS NULL
    OR (target_span_end IS NOT NULL AND target_span_end >= target_span_start)
  ),
  CHECK (
    ref_span_start IS NULL
    OR (ref_span_end IS NOT NULL AND ref_span_end >= ref_span_start)
  )
);

CREATE INDEX idx_error_candidates_segment ON error_candidates (segment_id);
CREATE INDEX idx_error_candidates_status ON error_candidates (status);
CREATE INDEX idx_error_candidates_external ON error_candidates (external_id);

CREATE TRIGGER trg_error_candidates_updated_at
  BEFORE UPDATE ON error_candidates
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ---------------------------------------------------------------------------
-- Batches and assignments
-- ---------------------------------------------------------------------------

CREATE TABLE batches (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  language_pair_id uuid NOT NULL REFERENCES language_pairs (id),
  owner_id uuid NOT NULL REFERENCES profiles (id),
  batch_number integer NOT NULL,
  status batch_status NOT NULL DEFAULT 'active',
  last_position integer NOT NULL DEFAULT 1,
  claimed_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  released_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (language_pair_id, batch_number)
);

CREATE UNIQUE INDEX idx_batches_one_active_per_user
  ON batches (owner_id)
  WHERE status = 'active';

CREATE INDEX idx_batches_owner_status ON batches (owner_id, status);
CREATE INDEX idx_batches_pair ON batches (language_pair_id);

CREATE TRIGGER trg_batches_updated_at
  BEFORE UPDATE ON batches
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE batch_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES batches (id) ON DELETE CASCADE,
  segment_id uuid NOT NULL REFERENCES segments (id),
  position integer NOT NULL,
  UNIQUE (batch_id, position),
  UNIQUE (batch_id, segment_id)
);

CREATE INDEX idx_batch_items_segment ON batch_items (segment_id);
CREATE INDEX idx_batch_items_batch ON batch_items (batch_id, position);

-- Pin exact candidate versions at claim time so later imports cannot change
-- in-flight or overlap assignments.
CREATE TABLE batch_item_candidates (
  batch_item_id uuid NOT NULL REFERENCES batch_items (id) ON DELETE CASCADE,
  candidate_id uuid NOT NULL REFERENCES error_candidates (id),
  PRIMARY KEY (batch_item_id, candidate_id)
);

CREATE INDEX idx_bic_candidate ON batch_item_candidates (candidate_id);

-- ---------------------------------------------------------------------------
-- Annotations
-- ---------------------------------------------------------------------------

CREATE TABLE annotations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_id uuid NOT NULL REFERENCES error_candidates (id),
  annotator_id uuid NOT NULL REFERENCES profiles (id),
  batch_id uuid NOT NULL REFERENCES batches (id),
  status annotation_status NOT NULL DEFAULT 'draft',
  edited_text text NOT NULL,
  error_type error_type NOT NULL,
  severity severity NOT NULL,
  rejection_reason rejection_reason,
  comment text,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (candidate_id, annotator_id),
  CHECK (
    (status = 'rejected' AND rejection_reason IS NOT NULL)
    OR (status <> 'rejected')
  )
);

CREATE INDEX idx_annotations_annotator ON annotations (annotator_id);
CREATE INDEX idx_annotations_batch ON annotations (batch_id);
CREATE INDEX idx_annotations_status ON annotations (status);

CREATE TRIGGER trg_annotations_updated_at
  BEFORE UPDATE ON annotations
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE annotation_history (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  annotation_id uuid NOT NULL REFERENCES annotations (id) ON DELETE CASCADE,
  rev integer NOT NULL,
  snapshot jsonb NOT NULL,
  changed_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (annotation_id, rev)
);

CREATE INDEX idx_annotation_history_ann ON annotation_history (annotation_id, rev);

CREATE TABLE error_suggestions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  segment_id uuid NOT NULL REFERENCES segments (id),
  batch_id uuid NOT NULL REFERENCES batches (id),
  author_id uuid NOT NULL REFERENCES profiles (id),
  suggested_text text NOT NULL,
  error_type error_type NOT NULL,
  severity severity NOT NULL,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_error_suggestions_segment ON error_suggestions (segment_id);
CREATE INDEX idx_error_suggestions_author ON error_suggestions (author_id);

CREATE TABLE admin_audit_log (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id uuid REFERENCES profiles (id),
  action text NOT NULL,
  entity text NOT NULL,
  entity_id uuid,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_admin_audit_log_created ON admin_audit_log (created_at DESC);

-- Last remaining active admin cannot be demoted or deactivated.
CREATE OR REPLACE FUNCTION protect_last_admin()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.role = 'admin' AND OLD.is_active THEN
      IF (SELECT count(*) FROM profiles WHERE role = 'admin' AND is_active AND id <> OLD.id) = 0 THEN
        RAISE EXCEPTION 'Cannot remove the final active administrator';
      END IF;
    END IF;
    RETURN OLD;
  END IF;

  IF OLD.role = 'admin' AND OLD.is_active
     AND (NEW.role IS DISTINCT FROM 'admin' OR NEW.is_active IS DISTINCT FROM TRUE) THEN
    IF (SELECT count(*) FROM profiles WHERE role = 'admin' AND is_active AND id <> OLD.id) = 0 THEN
      RAISE EXCEPTION 'Cannot remove the final active administrator';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

CREATE TRIGGER trg_protect_last_admin
  BEFORE UPDATE OR DELETE ON profiles
  FOR EACH ROW EXECUTE FUNCTION protect_last_admin();
