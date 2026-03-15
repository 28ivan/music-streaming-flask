-- Activar el soporte para claves foráneas en SQLite (Crucial para la integridad referencial)
PRAGMA foreign_keys = ON;

-- ============================================================================
-- TABLA: users
-- ============================================================================
-- Cumple con el requisito de tener usuarios estándar y administradores.
-- El registro asignará el rol por defecto, y la identificación será única.
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,

    full_name TEXT NOT NULL,
    country TEXT NOT NULL,

    -- Nuevo campo para el teléfono
    phone TEXT NOT NULL,

    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'USER' CHECK(role IN ('USER', 'ADMIN')),
    is_approved INTEGER NOT NULL DEFAULT 0 CHECK(is_approved IN (0, 1)),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- TABLA: songs
-- ============================================================================
-- Catálogo general de elementos (canciones).
-- El rol administrador será responsable de las Altas, Bajas y Modificaciones de esta tabla.
CREATE TABLE songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    title TEXT NOT NULL,
    artist TEXT NOT NULL,

    -- Álbum y URL pueden ser nulos si es un single o no hay enlace disponible.
    album TEXT,
    url TEXT,

    -- SQLite no tiene un tipo de dato nativo para fechas o tiempos exactos.
    -- Usamos INTEGER para la duración en segundos (fácil de calcular) y TEXT para la fecha (formato ISO 8601: YYYY-MM-DD).
    duration_seconds INTEGER CHECK(duration_seconds > 0),
    release_date TEXT
);

-- ============================================================================
-- TABLA: playlists
-- ============================================================================
-- Permite al rol de usuario estándar confeccionar un listado personal.
CREATE TABLE playlists (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Clave foránea que relaciona la lista con su creador.
    -- ON DELETE CASCADE: Si se borra un usuario, sus listas desaparecen (integridad).
    user_id INTEGER NOT NULL,
    name TEXT NOT NULL,

    created_at TEXT DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- ============================================================================
-- TABLA: playlist_songs
-- ============================================================================
-- Tabla intermedia para la relación Muchos a Muchos entre playlists y canciones.
-- Permite a los usuarios marcar/guardar/seleccionar elementos a partir del listado general.
CREATE TABLE playlist_songs (
    playlist_id INTEGER NOT NULL,
    song_id INTEGER NOT NULL,

    added_at TEXT DEFAULT CURRENT_TIMESTAMP,

    -- Clave primaria compuesta para evitar que una misma canción se añada dos veces a la misma lista de forma redundante.
    PRIMARY KEY (playlist_id, song_id),

    -- Integridad referencial:
    -- Si se borra una lista, se borran sus referencias.
    FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,

    -- Si un administrador borra una canción del catálogo general, esta desaparece automáticamente de las listas de los usuarios.
    FOREIGN KEY (song_id) REFERENCES songs(id) ON DELETE CASCADE
);