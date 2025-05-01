-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create a table for storing telegram messages with embeddings
CREATE TABLE IF NOT EXISTS telegram_messages (
    id SERIAL PRIMARY KEY,
    chat_title VARCHAR(255) NOT NULL,
    message_text TEXT NOT NULL,
    message_id BIGINT NOT NULL,
    sender_id BIGINT,
    embedding vector(384),  -- For all-MiniLM-L6-v2 embeddings (384 dimensions)
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on common search fields
CREATE INDEX IF NOT EXISTS idx_telegram_messages_chat_title ON telegram_messages(chat_title);
CREATE INDEX IF NOT EXISTS idx_telegram_messages_timestamp ON telegram_messages(timestamp);

-- Create vector index for similarity search
CREATE INDEX IF NOT EXISTS idx_telegram_messages_embedding ON telegram_messages USING ivfflat (embedding vector_cosine_ops);

-- Create a table for storing wishlist items from Mercado Livre
CREATE TABLE IF NOT EXISTS wishlist (
    id SERIAL PRIMARY KEY,
    url TEXT NOT NULL,
    title TEXT,
    price DECIMAL(10,2),
    added_by BIGINT,
    added_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Create index on wishlist table
CREATE INDEX IF NOT EXISTS idx_wishlist_added_at ON wishlist(added_at);

-- Create a table for storing coupons
CREATE TABLE IF NOT EXISTS coupons (
    id SERIAL PRIMARY KEY,
    code VARCHAR(50) NOT NULL UNIQUE,
    discount_value DECIMAL(10,2),
    discount_percentage DECIMAL(5,2),
    max_discount DECIMAL(10,2),
    discount_type VARCHAR(20) NOT NULL,
    minimun_purchase DECIMAL(10,2),
    product_type_limit VARCHAR(100),
    used BOOLEAN DEFAULT FALSE,
    date_created TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    date_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
);

-- Create indexes for coupons table
CREATE INDEX IF NOT EXISTS idx_coupons_code ON coupons(code);
CREATE INDEX IF NOT EXISTS idx_coupons_used ON coupons(used);
CREATE INDEX IF NOT EXISTS idx_coupons_date_created ON coupons(date_created); 