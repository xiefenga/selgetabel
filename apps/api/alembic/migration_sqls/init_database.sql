CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 648d4ca39b77

CREATE TABLE btracks (
    id UUID NOT NULL, 
    reporter_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    steps JSONB NOT NULL, 
    generation_prompt TEXT NOT NULL, 
    errors TEXT NOT NULL, 
    thread_turn_id UUID NOT NULL, 
    cause TEXT, 
    fixed BOOLEAN NOT NULL, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_btracks_id ON btracks (id);

CREATE INDEX ix_btracks_reporter_id ON btracks (reporter_id);

CREATE TABLE permissions (
    id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    code VARCHAR(100) NOT NULL, 
    description VARCHAR(500), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_permissions_code ON permissions (code);

CREATE INDEX ix_permissions_id ON permissions (id);

CREATE TABLE roles (
    id UUID NOT NULL, 
    name VARCHAR(100) NOT NULL, 
    code VARCHAR(50) NOT NULL, 
    description VARCHAR(500), 
    is_system BOOLEAN NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_roles_code ON roles (code);

CREATE INDEX ix_roles_id ON roles (id);

CREATE INDEX ix_roles_is_system ON roles (is_system);

CREATE UNIQUE INDEX ix_roles_name ON roles (name);

CREATE TABLE users (
    id UUID NOT NULL, 
    username VARCHAR(255) NOT NULL, 
    avatar VARCHAR(512) NOT NULL, 
    status SMALLINT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    last_login_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_users_id ON users (id);

CREATE INDEX ix_users_status ON users (status);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE accounts (
    id UUID NOT NULL, 
    account_id VARCHAR(255) NOT NULL, 
    provider_id VARCHAR(50) NOT NULL, 
    user_id UUID NOT NULL, 
    access_token TEXT, 
    refresh_token TEXT, 
    id_token TEXT, 
    access_token_expires_at TIMESTAMP WITH TIME ZONE, 
    refresh_token_expires_at TIMESTAMP WITH TIME ZONE, 
    scope VARCHAR(255), 
    password VARCHAR(255), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_account_provider_account UNIQUE (provider_id, account_id)
);

CREATE INDEX ix_accounts_id ON accounts (id);

CREATE INDEX ix_accounts_provider_id ON accounts (provider_id);

CREATE INDEX ix_accounts_user_id ON accounts (user_id);

CREATE TABLE files (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    filename VARCHAR(255) NOT NULL, 
    file_path VARCHAR(512) NOT NULL, 
    file_size INTEGER NOT NULL, 
    md5 VARCHAR(32) NOT NULL, 
    mime_type VARCHAR(100), 
    uploaded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_files_id ON files (id);

CREATE INDEX ix_files_md5 ON files (md5);

CREATE INDEX ix_files_uploaded_at ON files (uploaded_at);

CREATE INDEX ix_files_user_id ON files (user_id);

CREATE TABLE refresh_tokens (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    token VARCHAR(512) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    is_revoked BOOLEAN NOT NULL, 
    device_info VARCHAR(255), 
    user_agent TEXT, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_refresh_tokens_expires_at ON refresh_tokens (expires_at);

CREATE INDEX ix_refresh_tokens_id ON refresh_tokens (id);

CREATE UNIQUE INDEX ix_refresh_tokens_token ON refresh_tokens (token);

CREATE INDEX ix_refresh_tokens_user_id ON refresh_tokens (user_id);

CREATE TABLE role_permissions (
    id UUID NOT NULL, 
    role_id UUID NOT NULL, 
    permission_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(permission_id) REFERENCES permissions (id) ON DELETE CASCADE, 
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    CONSTRAINT uq_role_permission UNIQUE (role_id, permission_id)
);

CREATE INDEX ix_role_permissions_permission_id ON role_permissions (permission_id);

CREATE INDEX ix_role_permissions_role_id ON role_permissions (role_id);

CREATE TABLE threads (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    title VARCHAR(255), 
    status VARCHAR(20) NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_threads_id ON threads (id);

CREATE INDEX ix_threads_status ON threads (status);

CREATE INDEX ix_threads_updated_at ON threads (updated_at);

CREATE INDEX ix_threads_user_id ON threads (user_id);

CREATE TABLE user_roles (
    id UUID NOT NULL, 
    user_id UUID NOT NULL, 
    role_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(role_id) REFERENCES roles (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
    CONSTRAINT uq_user_role UNIQUE (user_id, role_id)
);

CREATE INDEX ix_user_roles_role_id ON user_roles (role_id);

CREATE INDEX ix_user_roles_user_id ON user_roles (user_id);

CREATE TABLE thread_turns (
    id UUID NOT NULL, 
    thread_id UUID NOT NULL, 
    turn_number INTEGER NOT NULL, 
    user_query TEXT NOT NULL, 
    status VARCHAR(20) NOT NULL, 
    steps JSONB NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    started_at TIMESTAMP WITH TIME ZONE, 
    completed_at TIMESTAMP WITH TIME ZONE, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(thread_id) REFERENCES threads (id) ON DELETE CASCADE, 
    CONSTRAINT uq_thread_turn UNIQUE (thread_id, turn_number)
);

CREATE INDEX ix_thread_turns_created_at ON thread_turns (created_at);

CREATE INDEX ix_thread_turns_id ON thread_turns (id);

CREATE INDEX ix_thread_turns_status ON thread_turns (status);

CREATE INDEX ix_thread_turns_thread_id ON thread_turns (thread_id);

CREATE TABLE turn_files (
    id UUID NOT NULL, 
    turn_id UUID NOT NULL, 
    file_id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(file_id) REFERENCES files (id) ON DELETE CASCADE, 
    FOREIGN KEY(turn_id) REFERENCES thread_turns (id) ON DELETE CASCADE, 
    CONSTRAINT uq_turn_file UNIQUE (turn_id, file_id)
);

CREATE INDEX ix_turn_files_file_id ON turn_files (file_id);

CREATE INDEX ix_turn_files_turn_id ON turn_files (turn_id);

INSERT INTO alembic_version (version_num) VALUES ('648d4ca39b77') RETURNING alembic_version.version_num;

