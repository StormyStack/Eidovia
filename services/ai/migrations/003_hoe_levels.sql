ALTER TABLE document_chunks
  ADD COLUMN IF NOT EXISTS hoe_level SMALLINT,
  ADD COLUMN IF NOT EXISTS section_title TEXT;

CREATE INDEX IF NOT EXISTS idx_document_chunks_hoe_level
  ON document_chunks (hoe_level);