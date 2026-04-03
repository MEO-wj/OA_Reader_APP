-- migrations/001_init_generic_backend.sql
-- AI Agent 通用后端基线迁移（create-only）
-- 说明：此文件为全新数据库的基线迁移，不包含 DROP 语句
-- 策略：仅展示 CREATE TABLE，新库或清空库直接应用此基线

-- 启用必要扩展
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- OA 文章表
CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    unit TEXT,
    link TEXT NOT NULL UNIQUE,
    published_on DATE NOT NULL,
    content TEXT NOT NULL,
    summary TEXT NOT NULL,
    attachments JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_articles_published_on ON articles (published_on);
CREATE INDEX IF NOT EXISTS idx_articles_title_trgm ON articles USING gin (title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_articles_content_trgm ON articles USING gin (content gin_trgm_ops);
COMMENT ON TABLE articles IS 'OA文章表';

-- 文章向量表
CREATE TABLE IF NOT EXISTS vectors (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT REFERENCES articles(id) ON DELETE CASCADE,
    embedding vector(1024),
    published_on DATE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_vectors_published_on ON vectors (published_on);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vectors_article ON vectors(article_id);
CREATE INDEX IF NOT EXISTS idx_vectors_embedding_hnsw ON vectors USING hnsw (embedding vector_cosine_ops);
COMMENT ON TABLE vectors IS '文章向量表';

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
    user_id UUID NOT NULL,
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
    user_id UUID NOT NULL,
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
    user_id UUID UNIQUE NOT NULL,
    portrait_text TEXT,
    knowledge_text TEXT,
    preferences JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_profiles_user_id ON user_profiles(user_id);

-- 表注释
COMMENT ON TABLE articles IS 'OA文章表';
COMMENT ON TABLE vectors IS '文章向量表';
COMMENT ON TABLE skills IS '技能定义表，存储 SKILL.md 内容';
COMMENT ON TABLE skill_references IS '技能参考资料表，存储技能目录下的参考文件';
COMMENT ON TABLE conversations IS '对话记录表，存储用户与 AI 的对话历史';
COMMENT ON TABLE conversation_sessions IS '会话元信息表，存储会话基本信息';
COMMENT ON TABLE user_profiles IS '用户画像表，存储用户特征和偏好';
