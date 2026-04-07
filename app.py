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
UPLOAD_FOLDER = 'static/uploads/profiles' # Carpeta donde se guardarán
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'} # Extensiones permitidas

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Asegurar que la carpeta exista al arrancar
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

                # Guardar el archivo físicamente en la carpeta
                with open(filepath, "wb") as f:
                    f.write(file_data)

                # Actualizar la variable para guardar solo la ruta en SQLite
                db_pic_path = f"/{UPLOAD_FOLDER}/{filename}"
            except Exception as e:
                print(f"Error procesando imagen: {e}")
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

        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Usuario no encontrado o no autorizado"}), 404

        return jsonify({"message": "Perfil actualizado correctamente"}), 200

    except sqlite3.Error as e:
        return jsonify({"error": f"Error de base de datos: {str(e)}"}), 500
    finally:
        conn.close()


# ==========================================================
# ENDPOINT: Subir Foto de Perfil (NUEVO)
# ==========================================================
@app.route('/api/profile/<int:user_id>/upload-pic', methods=['POST'])
def upload_profile_pic(user_id):
    # Verificar si la petición trae un archivo
    if 'file' not in request.files:
        return jsonify({"error": "No se ha seleccionado ningún archivo"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    if file and allowed_file(file.filename):
        # Asegurar nombre de archivo seguro y único (usando el ID de usuario)
        filename = secure_filename(f"user_{user_id}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Guardar archivo en el disco
        file.save(filepath)

        # Ruta relativa para guardar en BD (empezando por /static)
        db_path = f"/{UPLOAD_FOLDER}/{filename}"

        # Actualizar Base de Datos
        conn = get_db_connection()
        try:
            conn.execute('UPDATE users SET profile_pic = ? WHERE id = ?', (db_path, user_id))
            conn.commit()
            return jsonify({
                "message": "Foto de perfil actualizada",
                "new_pic_url": db_path
            }), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500
        finally:
            conn.close()

    return jsonify({"error": "Tipo de archivo no permitido"}), 400


@app.route('/api/songs', methods=['GET', 'POST'])
def handle_songs():
    conn = get_db_connection()
    if request.method == 'GET':
        songs = conn.execute('SELECT * FROM songs').fetchall()
        conn.close()
        return jsonify([dict(s) for s in songs]), 200

    if request.method == 'POST':
        data = request.get_json()
        conn.execute('INSERT INTO songs (title, artist, album, duration_seconds) VALUES (?, ?, ?, ?)',
                     (data['title'], data['artist'], data.get('album'), data.get('duration_seconds')))
        conn.commit()
        conn.close()
        return jsonify({"message": "Canción añadida"}), 201


@app.route('/api/songs/<int:song_id>', methods=['DELETE'])
def delete_song(song_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM songs WHERE id = ?', (song_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Canción eliminada"}), 200


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


if __name__ == '__main__':
    app.run(debug=True, port=5000)