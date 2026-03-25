-- migrations/001_init_generic_backend.sql
-- AI Agent 通用后端基线迁移（create-only）
-- 说明：此文件为全新数据库的基线迁移，不包含 DROP 语句
-- 策略：仅展示 CREATE TABLE，新库或清空库直接应用此基线

-- 启用必要扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 文档表（通用文档存储，支持向量检索）
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    summary TEXT,
    source_type VARCHAR(50) DEFAULT 'markdown',
    embedding vector(1024),
    content_hash VARCHAR(64) UNIQUE,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 文档向量索引（HNSW）
CREATE INDEX IF NOT EXISTS idx_documents_embedding
ON documents USING hnsw (embedding vector_cosine_ops);

-- 文档 content_hash 索引
CREATE INDEX IF NOT EXISTS idx_documents_content_hash
ON documents (content_hash);

-- 文档标题模糊搜索索引（pg_trgm）
CREATE INDEX IF NOT EXISTS idx_documents_title_trgm
ON documents USING gin (title gin_trgm_ops);

-- 文档正文模糊搜索索引（pg_trgm）
CREATE INDEX IF NOT EXISTS idx_documents_content_trgm
ON documents USING gin (content gin_trgm_ops);

-- 技能定义表
CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    description TEXT,
    verification_token VARCHAR(100),
    metadata JSONB NOT NULL DEFAULT '{}',
    content TEXT NOT NULL,
    tools TEXT,
    is_static BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 技能参考资料表
CREATE TABLE IF NOT EXISTS skill_references (
    id SERIAL PRIMARY KEY,
    skill_id INTEGER REFERENCES skills(id) ON DELETE CASCADE,
    file_path VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(skill_id, file_path)
);

-- 对话记录表（按会话聚合存储）
CREATE TABLE IF NOT EXISTS conversations (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    title VARCHAR(256) DEFAULT '新会话',
    messages JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 对话索引
CREATE UNIQUE INDEX IF NOT EXISTS idx_conversations_user_conv
    ON conversations(user_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_conversations_created_at
    ON conversations(created_at);

-- 会话元信息表
CREATE TABLE IF NOT EXISTS conversation_sessions (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    conversation_id VARCHAR(64) NOT NULL,
    title VARCHAR(256) DEFAULT '新会话',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_user_conv
    ON conversation_sessions(user_id, conversation_id);

CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON conversation_sessions(user_id);

-- 用户画像表
CREATE TABLE IF NOT EXISTS user_profiles (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(64) UNIQUE NOT NULL,
    portrait_text TEXT,
    knowledge_text TEXT,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);

-- 表注释
COMMENT ON TABLE documents IS '通用文档表，存储可检索的文档内容及其向量表示';
COMMENT ON TABLE skills IS '技能定义表，存储 SKILL.md 内容';
COMMENT ON TABLE skill_references IS '技能参考资料表，存储技能目录下的参考文件';
COMMENT ON TABLE conversations IS '对话记录表，存储用户与 AI 的对话历史';
COMMENT ON TABLE conversation_sessions IS '会话元信息表，存储会话基本信息';
COMMENT ON TABLE user_profiles IS '用户画像表，存储用户特征和偏好';
