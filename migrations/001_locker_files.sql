-- Locker files table: tracks all files stored in user lockers
CREATE TABLE IF NOT EXISTS locker_files (
    file_id       SERIAL PRIMARY KEY,
    user_id       INTEGER NOT NULL REFERENCES users(user_id),
    upload_group  VARCHAR(64) NOT NULL,          -- groups files from same injection run
    file_type     VARCHAR(32) NOT NULL,          -- 'injected', 'manifest', 'heatmap', 'original', 'verify_report', 'pdf'
    file_name     VARCHAR(512) NOT NULL,
    file_path     VARCHAR(1024) NOT NULL,        -- relative path from lockers/
    mime_type     VARCHAR(128),
    file_size     BIGINT,
    image_hash    VARCHAR(64),
    profile       VARCHAR(64),
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_locker_files_user_id ON locker_files(user_id);
CREATE INDEX IF NOT EXISTS idx_locker_files_upload_group ON locker_files(upload_group);
