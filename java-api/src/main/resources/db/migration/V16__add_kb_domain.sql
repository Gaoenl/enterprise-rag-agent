-- V16: 知识库增加业务域（domain），用于意图 L1 路由。
ALTER TABLE kb_knowledge_base ADD COLUMN IF NOT EXISTS domain_code VARCHAR(32) NOT NULL DEFAULT 'GENERAL';

CREATE INDEX IF NOT EXISTS idx_kb_domain
    ON kb_knowledge_base (tenant_id, domain_code, deleted);