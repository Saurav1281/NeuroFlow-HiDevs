-- Enable RLS on all tables
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipelines ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE evaluations ENABLE ROW LEVEL SECURITY;
ALTER TABLE training_pairs ENABLE ROW LEVEL SECURITY;
ALTER TABLE finetune_jobs ENABLE ROW LEVEL SECURITY;

-- Note: pipeline_id in documents table.
-- chunks inherits document's pipeline_id conceptually, but for pure RLS without expensive joins we usually:
-- either denormalize pipeline_id to chunks, or use a join.
-- For simplicity, let's assume session role or current_setting sets app.pipeline_id.

-- For documents
CREATE POLICY documents_pipeline_isolation_policy
  ON documents
  USING (
    pipeline_id = current_setting('app.pipeline_id', true)::uuid
    OR current_setting('app.pipeline_id', true) IS NULL -- bypass for admin if needed
  );

-- For chunks: depends on document's pipeline_id
CREATE POLICY chunks_pipeline_isolation_policy
  ON chunks
  USING (
    EXISTS (
      SELECT 1 FROM documents d 
      WHERE d.id = chunks.document_id 
      AND (d.pipeline_id = current_setting('app.pipeline_id', true)::uuid 
           OR current_setting('app.pipeline_id', true) IS NULL)
    )
  );

-- For pipelines
CREATE POLICY pipelines_isolation_policy
  ON pipelines
  USING (
    id = current_setting('app.pipeline_id', true)::uuid
    OR current_setting('app.pipeline_id', true) IS NULL
  );

-- For pipeline_runs
CREATE POLICY pipeline_runs_isolation_policy
  ON pipeline_runs
  USING (
    pipeline_id = current_setting('app.pipeline_id', true)::uuid
    OR current_setting('app.pipeline_id', true) IS NULL
  );

-- For evaluations
CREATE POLICY evaluations_isolation_policy
  ON evaluations
  USING (
    EXISTS (
      SELECT 1 FROM pipeline_runs r
      WHERE r.id = evaluations.run_id
      AND (r.pipeline_id = current_setting('app.pipeline_id', true)::uuid
           OR current_setting('app.pipeline_id', true) IS NULL)
    )
  );

-- For training_pairs
CREATE POLICY training_pairs_isolation_policy
  ON training_pairs
  USING (
    EXISTS (
      SELECT 1 FROM pipeline_runs r
      WHERE r.id = training_pairs.run_id
      AND (r.pipeline_id = current_setting('app.pipeline_id', true)::uuid
           OR current_setting('app.pipeline_id', true) IS NULL)
    )
  );

-- For finetune_jobs
-- finetune_jobs lacks explicit pipeline_id linking except via runs, but we can assume tenant admin level.
-- If required, this could be customized.
