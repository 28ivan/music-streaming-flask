import base64
import os
import uuid

from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)
DATABASE = 'database/music.sqlite'

# CONFIGURACIÓN DE SUBIDA DE IMÁGENES
BASE_UPLOAD_FOLDER = 'static/uploads' # Carpeta base
PROFILES_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'profiles') # Perfiles
COVERS_UPLOAD_FOLDER = os.path.join(BASE_UPLOAD_FOLDER, 'covers')     # NUEVO: Portadas
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} # Extensiones permitidas

# Asegurar que la carpeta exista al arrancar
os.makedirs(PROFILES_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COVERS_UPLOAD_FOLDER, exist_ok=True) # NUEVO

app.config['PROFILES_UPLOAD_FOLDER'] = PROFILES_UPLOAD_FOLDER
app.config['COVERS_UPLOAD_FOLDER'] = COVERS_UPLOAD_FOLDER # NUEVO

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    try:
        password_hash = generate_password_hash(data['password'])

        # --- NUEVA LÓGICA: Procesar imagen Base64 a archivo físico ---
        raw_pic = data.get('profile_pic', '/static/fotoPersona.png')
        db_pic_path = raw_pic  # Por defecto, la ruta o el Base64

        # Si la imagen viene como texto Base64 (empieza por data:image...)
        if raw_pic and raw_pic.startswith('data:image'):
            try:
                # Separar la cabecera (data:image/png;base64) del contenido real
                header, encoded = raw_pic.split(",", 1)
                # Extraer la extensión del archivo (png, jpeg, etc.)
                ext = header.split(';')[0].split('/')[1]

                # Decodificar el texto a formato binario (imagen real)
                file_data = base64.b64decode(encoded)

                # Generar un nombre único para evitar que dos usuarios sobrescriban "foto.png"
                filename = f"reg_{uuid.uuid4().hex[:8]}.{ext}"

                # CORRECCIÓN 1: Usar la carpeta específica de perfiles
                filepath = os.path.join(app.config['PROFILES_UPLOAD_FOLDER'], filename)

                # Guardar el archivo físicamente en la carpeta
                with open(filepath, "wb") as f:
                    f.write(file_data)

                # CORRECCIÓN 2: Forzar barras normales para la web (URL estática)
                db_pic_path = f"/static/uploads/profiles/{filename}"

            except Exception as e:
                import traceback
                traceback.print_exc()  # Esto te mostrará el error real en la consola si algo falla
                db_pic_path = '/static/fotoPersona.png'  # Fallback si algo falla
        # -------------------------------------------------------------

        conn = get_db_connection()
        conn.execute('''
                     INSERT INTO users (email, username, password_hash, name, surname1, surname2, birth_date,
                                        description, profile_pic)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ''', (data['email'], data['username'], password_hash, data['name'], data['surname1'],
                           data.get('surname2', ''), data['birth_date'], data.get('description', ''), db_pic_path))
        conn.commit()
        conn.close()

        return jsonify(
            {"message": "Registro exitoso. Tu cuenta está pendiente de aprobación por un administrador."}), 201

    except sqlite3.IntegrityError:
        return jsonify({"error": "Email o Usuario ya registrados"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE email = ?', (data.get('email'),)).fetchone()
    conn.close()

    if user and check_password_hash(user['password_hash'], data.get('password')):
        # RESTAURADO: Validación de cuenta aprobada
        if user['is_approved'] == 0:
            return jsonify({"error": "Acceso denegado: Tu cuenta aún debe ser aprobada por un administrador."}), 403

        return jsonify({"message": "Login exitoso", "user": dict(user)}), 200
    return jsonify({"error": "Credenciales incorrectas"}), 401


@app.route('/api/profile/<int:user_id>', methods=['GET'])
def profile(user_id):
    conn = get_db_connection()
    user = conn.execute(
        'SELECT email, username, name, surname1, surname2, birth_date, description, role, profile_pic FROM users WHERE id = ?',
        (user_id,)).fetchone()
    conn.close()
    return jsonify(dict(user)) if user else (jsonify({"error": "No encontrado"}), 404)


# ==========================================================
# ENDPOINT: Actualizar Perfil de Usuario (CORREGIDO)
# ==========================================================
@app.route('/api/profile/<int:user_id>', methods=['PUT'])
def update_profile(user_id):
    data = request.get_json()

    # Extraemos los campos exactos que nos manda index.html
    name = data.get('name')
    surname1 = data.get('surname1')
    surname2 = data.get('surname2')
    birth_date = data.get('birth_date')
    description = data.get('description')
    password = data.get('password')

    # Validación básica (obligatorios según tu schema)
    if not name or not surname1 or not birth_date:
        return jsonify({"error": "Nombre, Primer Apellido y Fecha de Nacimiento son obligatorios"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Ejecutamos la actualización SQL con las columnas correctas
        cursor.execute('''
                       UPDATE users
                       SET name        = ?,
                           surname1    = ?,
                           surname2    = ?,
                           birth_date  = ?,
                           description = ?
                       WHERE id = ?
                       ''', (name, surname1, surname2, birth_date, description, user_id))

        # 2. Si el usuario escribió algo en el campo password, la actualizamos hasheada
        if password and password.strip() != "":
            new_hash = generate_password_hash(password)
            cursor.execute('UPDATE users SET password_hash = ? WHERE id = ?', (new_hash, user_id))

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Usuario no encontrado o no autorizado"}), 404

        return jsonify({"message": "Perfil actualizado correctamente"}), 200

    except sqlite3.Error as e:
        return jsonify({"error": f"Error de base de datos: {str(e)}"}), 500
    finally:
        conn.close()


# ==========================================================
# ENDPOINT: Subir Foto de Perfil (CORREGIDO)
# ==========================================================
@app.route('/api/profile/<int:user_id>/upload-pic', methods=['POST'])
def upload_profile_pic(user_id):
    try:
        # Verificar si la petición trae un archivo
        if 'file' not in request.files:
            return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({"error": "Nombre de archivo vacío"}), 400

        if file and allowed_file(file.filename):
            # Asegurar nombre de archivo seguro y único
            filename = secure_filename(f"user_{user_id}_{file.filename}")

            # CORRECCIÓN 1: Usar la carpeta específica de perfiles
            filepath = os.path.join(app.config['PROFILES_UPLOAD_FOLDER'], filename)

            # Guardar archivo en el disco
            file.save(filepath)

            # CORRECCIÓN 2: Forzar barras normales para la web (URL estática)
            db_path = f"/static/uploads/profiles/{filename}"

            # Actualizar Base de Datos
            conn = get_db_connection()
            conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (db_path, user_id))
            conn.commit()
            conn.close()

            return jsonify({
                "message": "Foto de perfil actualizada",
                "new_pic_url": db_path
            }), 200

        return jsonify({"error": "Tipo de archivo no permitido"}), 400

    except Exception as e:
        # Capturamos cualquier error de guardado y lo mostramos en consola
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Error interno guardando la imagen: {str(e)}"}), 500


@app.route('/api/songs', methods=['GET', 'POST'])
def handle_songs():
    conn = get_db_connection()

    # === OBTENER CATÁLOGO ===
    if request.method == 'GET':
        songs = conn.execute('SELECT * FROM songs').fetchall()
        conn.close()
        return jsonify([dict(s) for s in songs]), 200

    # === AÑADIR NUEVA CANCIÓN ===
    if request.method == 'POST':
        data = request.get_json()

        # --- NUEVA LÓGICA: Procesar imagen Base64 de la portada a archivo físico ---
        raw_cover = data.get('cover_pic', '/static/fotoCancion.png')
        db_cover_path = raw_cover  # Por defecto, la ruta o el Base64

        if raw_cover and raw_cover.startswith('data:image'):
            try:
                # Separar cabecera y decodificar
                header, encoded = raw_cover.split(",", 1)
                ext = header.split(';')[0].split('/')[1]
                file_data = base64.b64decode(encoded)

                # Generar nombre único y guardar en la carpeta de COVERS
                filename = f"cover_{uuid.uuid4().hex[:8]}.{ext}"
                filepath = os.path.join(app.config['COVERS_UPLOAD_FOLDER'], filename)

                with open(filepath, "wb") as f:
                    f.write(file_data)

                # Actualizar variable para guardar solo la ruta
                db_cover_path = f"/static/uploads/covers/{filename}"
            except Exception as e:
                import traceback
                traceback.print_exc()
                db_cover_path = '/static/fotoPersona.png'  # Fallback si falla
        # -------------------------------------------------------------------------

        try:
            conn.execute('''
                         INSERT INTO songs
                         (title, artist, album, duration_seconds, track_number, release_year, song_description,
                          cover_pic)
                         VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                         ''', (
                             data['title'],
                             data['artist'],
                             data.get('album'),
                             data.get('duration_seconds'),
                             data.get('track_number'),
                             data.get('release_year'),
                             data.get('song_description'),
                             db_cover_path  # Usamos la nueva variable con la ruta limpia
                         ))

            conn.commit()
            return jsonify({"message": "Canción añadida exitosamente"}), 201
        except Exception as e:
            return jsonify({"error": str(e)}), 400
        finally:
            conn.close()


# ==========================================================
# ENDPOINT: Obtener detalles de UNA canción (NUEVO)
# ==========================================================
@app.route('/api/songs/<int:song_id>', methods=['GET'])
def get_song_details(song_id):
    conn = get_db_connection()
    # Buscamos todos los campos de la canción por su ID
    song = conn.execute('SELECT * FROM songs WHERE id = ?', (song_id,)).fetchone()
    conn.close()

    if song:
        # Si existe, la convertimos a diccionario y la enviamos como JSON
        return jsonify(dict(song)), 200
    else:
        # Si no existe, devolvemos un error 404
        return jsonify({"error": "Canción no encontrada"}), 404


@app.route('/api/songs/<int:song_id>', methods=['DELETE'])
def delete_song(song_id):
    conn = get_db_connection()

    # NUEVA LÓGICA: Comprobar si la canción está en alguna lista de reproducción
    # Contamos cuántas veces aparece esta canción en la tabla intermedia de listas
    in_playlists = conn.execute('SELECT COUNT(*) as count FROM playlist_songs WHERE song_id = ?', (song_id,)).fetchone()

    # Si la cuenta es mayor a 0, detenemos la eliminación y enviamos un error 409 (Conflicto)
    if in_playlists['count'] > 0:
        conn.close()
        return jsonify({"error": "No se puede eliminar: Esta canción está incluida en al menos una lista de reproducción de un usuario."}), 409

    # Si no está en ninguna lista, procedemos a borrarla del catálogo general
    conn.execute('DELETE FROM songs WHERE id = ?', (song_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Canción eliminada del catálogo"}), 200


@app.route('/api/favorites/<int:user_id>', methods=['GET', 'POST', 'DELETE'])
def handle_favorites(user_id):
    conn = get_db_connection()
    if request.method == 'GET':
        songs = conn.execute('''
                             SELECT s.*
                             FROM songs s
                                      JOIN favorites f ON s.id = f.song_id
                             WHERE f.user_id = ?
                             ''', (user_id,)).fetchall()
        conn.close()
        return jsonify([dict(s) for s in songs]), 200

    if request.method == 'POST':
        data = request.get_json()
        try:
            conn.execute('INSERT INTO favorites (user_id, song_id) VALUES (?, ?)', (user_id, data['song_id']))
            conn.commit()
        except sqlite3.IntegrityError:
            pass
        finally:
            conn.close()
        return jsonify({"message": "Añadido a favoritos"}), 201
# ==========================================================
# US-4: ELIMINAR CANCIÓN DE FAVORITOS
# ==========================================================
@app.route('/api/favorites/<int:user_id>/<int:song_id>', methods=['DELETE'])
def delete_favorite(user_id, song_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM favorites WHERE user_id = ? AND song_id = ?', (user_id, song_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Eliminado de favoritos"}), 200

## Para la US 5. Obtener usuarios pendientes de aprobacion
@app.route('/api/admin/pending_users', methods=['GET'])
def get_pending_users():
    conn = get_db_connection()
    # Buscamos usuarios no aprobados y que tengan rol USER
    users = conn.execute('''
        SELECT id, username, email, name, surname1, created_at, profile_pic
        FROM users 
        WHERE is_approved = 0 AND role = 'USER'
    ''').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users]), 200

##US 5. Aprobar y denegar cuentas
@app.route('/api/admin/approve/<int:user_id>', methods=['POST'])
def approve_user(user_id):
    conn = get_db_connection()
    conn.execute('UPDATE users SET is_approved = 1 WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Usuario aprobado con éxito"}), 200

@app.route('/api/admin/reject/<int:user_id>', methods=['DELETE'])
def reject_user(user_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Petición denegada y usuario eliminado"}), 200

# US-4: GESTIÓN DE LISTAS DE REPRODUCCIÓN (PLAYLISTS)
@app.route('/api/playlists/<int:user_id>', methods=['GET', 'POST'])
def handle_playlists(user_id):
    conn = get_db_connection()

    # 1. OBTENER LAS LISTAS DE UN USUARIO
    if request.method == 'GET':
        playlists = conn.execute('SELECT * FROM playlists WHERE user_id = ?', (user_id,)).fetchall()
        conn.close()
        return jsonify([dict(p) for p in playlists]), 200

    # 2. CREAR UNA NUEVA LISTA
    if request.method == 'POST':
        data = request.get_json()
        playlist_name = data.get('name')

        if not playlist_name:
            conn.close()
            return jsonify({"error": "El nombre de la lista es obligatorio"}), 400

        # --- NUEVA VALIDACIÓN: Evitar nombres repetidos ---
        existing_playlist = conn.execute(
            'SELECT id FROM playlists WHERE user_id = ? AND name = ?',
            (user_id, playlist_name)
        ).fetchone()

        if existing_playlist:
            conn.close()
            return jsonify({"error": f"Ya tienes una lista llamada '{playlist_name}'. ¡Elige otro nombre!"}), 400

        cursor = conn.cursor()
        cursor.execute('INSERT INTO playlists (user_id, name) VALUES (?, ?)', (user_id, playlist_name))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()

        return jsonify({"message": "Lista creada con éxito", "id": new_id, "name": playlist_name}), 201


# 3. AÑADIR CANCIÓN A UNA LISTA
@app.route('/api/playlists/<int:playlist_id>/songs', methods=['POST'])
def add_song_to_playlist(playlist_id):
    data = request.get_json()
    song_id = data.get('song_id')

    if not song_id:
        return jsonify({"error": "El ID de la canción es obligatorio"}), 400

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO playlist_songs (playlist_id, song_id) VALUES (?, ?)', (playlist_id, song_id))
        conn.commit()
        return jsonify({"message": "Canción añadida a la lista"}), 201
    except sqlite3.IntegrityError:
        # Si salta este error, es que la combinación playlist_id y song_id ya existe
        return jsonify({"error": "La canción ya está en esta lista"}), 409
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


# 4. ELIMINAR UNA LISTA COMPLETA
@app.route('/api/playlists/<int:playlist_id>', methods=['DELETE'])
def delete_playlist(playlist_id):
    conn = get_db_connection()
    # Gracias al "ON DELETE CASCADE" del SQL, al borrar la lista se borran sus canciones de la tabla intermedia
    conn.execute('DELETE FROM playlists WHERE id = ?', (playlist_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Lista eliminada correctamente"}), 200

# 5. OBTENER LAS CANCIONES DE UNA LISTA ESPECÍFICA
@app.route('/api/playlists/<int:playlist_id>/songs', methods=['GET'])
def get_playlist_songs(playlist_id):
    conn = get_db_connection()
    songs = conn.execute('''
        SELECT s.* FROM songs s
        JOIN playlist_songs ps ON s.id = ps.song_id
        WHERE ps.playlist_id = ?
        ORDER BY ps.added_at DESC
    ''', (playlist_id,)).fetchall()
    conn.close()
    return jsonify([dict(s) for s in songs]), 200

# 6. ELIMINAR UNA CANCIÓN DE UNA LISTA
@app.route('/api/playlists/<int:playlist_id>/songs/<int:song_id>', methods=['DELETE'])
def remove_song_from_playlist(playlist_id, song_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM playlist_songs WHERE playlist_id = ? AND song_id = ?', (playlist_id, song_id))
    conn.commit()
    conn.close()
    return jsonify({"message": "Canción eliminada de la lista"}), 200

# 7. OBTENER LISTAS CON EL ESTADO DE UNA CANCIÓN ESPECÍFICA (Saber si ya está dentro)
@app.route('/api/playlists/<int:user_id>/check_song/<int:song_id>', methods=['GET'])
def get_playlists_with_song_status(user_id, song_id):
    conn = get_db_connection()
    # Usamos LEFT JOIN para obtener un 1 o 0 si la canción está dentro de cada lista
    playlists = conn.execute('''
        SELECT p.*, 
               CASE WHEN ps.song_id IS NOT NULL THEN 1 ELSE 0 END as contains_song
        FROM playlists p
        LEFT JOIN playlist_songs ps ON p.id = ps.playlist_id AND ps.song_id = ?
        WHERE p.user_id = ?
    ''', (song_id, user_id)).fetchall()
    conn.close()
    return jsonify([dict(p) for p in playlists]), 200


# ==========================================================
# ENDPOINT: Actualizar información de UNA canción (NUEVO)
# ==========================================================
@app.route('/api/songs/<int:song_id>', methods=['PUT'])
def update_song(song_id):
    data = request.get_json()

    # Extraemos datos básicos obligatorios y opcionales
    title = data.get('title')
    artist = data.get('artist')
    album = data.get('album')
    duration_seconds = data.get('duration_seconds')
    track_number = data.get('track_number')
    release_year = data.get('release_year')
    song_description = data.get('song_description')

    if not title or not artist:
        return jsonify({"error": "El Título y el Artista son obligatorios"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Recuperamos la portada actual por si el admin no ha subido una nueva
        current_song = cursor.execute('SELECT cover_pic FROM songs WHERE id = ?', (song_id,)).fetchone()
        if not current_song:
            return jsonify({"error": "Canción no encontrada"}), 404

        db_cover_path = current_song['cover_pic']

        # --- LÓGICA: Procesar nueva imagen Base64 a archivo físico ---
        raw_cover = data.get('cover_pic')
        if raw_cover and raw_cover.startswith('data:image'):
            try:
                header, encoded = raw_cover.split(",", 1)
                ext = header.split(';')[0].split('/')[1]
                file_data = base64.b64decode(encoded)

                filename = f"cover_{uuid.uuid4().hex[:8]}.{ext}"
                filepath = os.path.join(app.config['COVERS_UPLOAD_FOLDER'], filename)

                with open(filepath, "wb") as f:
                    f.write(file_data)

                db_cover_path = f"/static/uploads/covers/{filename}"
            except Exception as e:
                import traceback
                traceback.print_exc()
        # -------------------------------------------------------------

        # Ejecutamos la actualización SQL
        cursor.execute('''
            UPDATE songs
            SET title = ?, artist = ?, album = ?, duration_seconds = ?,
                track_number = ?, release_year = ?, song_description = ?, cover_pic = ?
            WHERE id = ?
        ''', (title, artist, album, duration_seconds, track_number, release_year, song_description, db_cover_path,
              song_id))

        conn.commit()
        return jsonify({"message": "Información de la canción actualizada correctamente"}), 200

    except sqlite3.Error as e:
        return jsonify({"error": f"Error de base de datos: {str(e)}"}), 500
    finally:
        conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5000)