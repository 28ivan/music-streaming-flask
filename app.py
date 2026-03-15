from flask import Flask, request, jsonify, render_template
from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Permitir peticiones desde el Frontend (CORS)
CORS(app)

# Ruta a la base de datos que creamos en el paso anterior
DATABASE = 'database/music.sqlite'


# ==========================================================
# ENDPOINT: Servir el Frontend (SPA)
# ==========================================================
@app.route('/')
def index():
    # Flask buscará automáticamente este archivo en la carpeta 'templates'
    return render_template('index.html')


def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    # Forzar el soporte de claves foráneas por cada conexión
    conn.execute('PRAGMA foreign_keys = ON;')
    return conn


# ==========================================================
# ENDPOINT: Registro de usuarios
# ==========================================================
@app.route('/api/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    full_name = data.get('full_name')
    country = data.get('country')
    phone = data.get('phone') # Recuperamos el teléfono
    password = data.get('password')

    # Añadimos 'phone' a la validación de campos obligatorios
    if not username or not email or not password or not full_name or not country or not phone:
        return jsonify({"error": "Todos los campos son obligatorios"}), 400

    password_hash = generate_password_hash(password)

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Añadimos 'phone' a la consulta SQL
        cursor.execute(
            'INSERT INTO users (username, email, full_name, country, phone, password_hash) VALUES (?, ?, ?, ?, ?, ?)',
            (username, email, full_name, country, phone, password_hash)
        )
        conn.commit()
        return jsonify({"message": "Registro exitoso. Tu cuenta está pendiente de aprobación."}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "El nombre de usuario o correo ya están registrados."}), 409
    finally:
        conn.close()


# ==========================================================
# ENDPOINT: Inicio de sesión
# ==========================================================
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"error": "Faltan credenciales"}), 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Buscar al usuario por su email
    user = cursor.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    conn.close()

    # Validar si el usuario existe
    if user is None:
        return jsonify({"error": "Credenciales incorrectas"}), 401

    # Validar contraseña
    if not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Credenciales incorrectas"}), 401

    # VALIDACIÓN CLAVE: Aprobación manual
    if user['is_approved'] == 0:
        return jsonify({"error": "Acceso denegado: Tu cuenta aún debe ser aprobada por un administrador."}), 403

    # Si todos es correcto, devolver éxito (Aquí idealmente devolveríamos un JWT)
    return jsonify({
        "message": "Login exitoso",
        "user": {
            "id": user['id'],
            "username": user['username'],
            "role": user['role']
        }
    }), 200


# ==========================================================
# ENDPOINT: Obtener el catálogo general de canciones
# ==========================================================
@app.route('/api/songs', methods=['GET'])
def get_songs():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Consultamos todas las canciones
    songs = cursor.execute('SELECT * FROM songs').fetchall()
    conn.close()

    # Convertimos las filas de SQLite en una lista de diccionarios (JSON)
    songs_list = []
    for song in songs:
        songs_list.append({
            "id": song['id'],
            "title": song['title'],
            "artist": song['artist'],
            "album": song['album'],
            "duration": song['duration_seconds'],
            "release_date": song['release_date']
        })

    return jsonify(songs_list), 200


# ==========================================================
# ENDPOINT: Obtener Perfil de Usuario
# ==========================================================
@app.route('/api/profile/<int:user_id>', methods=['GET'])
def get_profile(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Añadimos 'phone' a la lista de columnas seleccionadas
    user = cursor.execute('''
                          SELECT username, email, full_name, country, phone, role, created_at
                          FROM users
                          WHERE id = ?
                          ''', (user_id,)).fetchone()

    conn.close()

    if user is None:
        return jsonify({"error": "Usuario no encontrado"}), 404

    return jsonify(dict(user)), 200


if __name__ == '__main__':
    # Ejecutar la API en el puerto 5000
    app.run(debug=True, port=5000)