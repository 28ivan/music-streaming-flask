PRAGMA foreign_keys = ON;

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    
    name TEXT NOT NULL,
    surname1 TEXT NOT NULL,
    surname2 TEXT,
    birth_date TEXT NOT NULL,
    description TEXT,

    profile_pic TEXT DEFAULT '/static/fotoPersona.png',

    role TEXT NOT NULL DEFAULT 'USER' CHECK(role IN ('USER', 'ADMIN')),
    -- RESTAURADO: Campo de aprobación manual (por defecto 0)
    is_approved INTEGER NOT NULL DEFAULT 0 CHECK(is_approved IN (0, 1)),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    album TEXT,
    duration_seconds INTEGER
);

CREATE TABLE favorites (
    user_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,
    added_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, song_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);

-- Administrador por defecto (IMPORTANTE: Le pasamos un 1 en is_approved para que pueda entrar)
INSERT INTO users (email, username, password_hash, name, surname1, birth_date, role, is_approved)
VALUES ('admin@music.com', 'admin', 'scrypt:32768:8:1$Ku6tiMHXvyMgOQK9$33a6e21bdc8a9298f9c39e7f978cc3f134046a708f184f890e6935f0be714af9d5e0bc7a96cacbda29fd41c49cc2c77918e91b33e72cb680e766c9b1a989e26f', 'Admin', 'Root', '2000-01-01', 'ADMIN', 1);