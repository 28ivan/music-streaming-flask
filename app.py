from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
CORS(app)
DATABASE = 'database/music.sqlite'


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
        profile_pic = data.get('profile_pic', '/static/fotoPersona.png')

        conn = get_db_connection()
        conn.execute('''
                     INSERT INTO users (email, username, password_hash, name, surname1, surname2, birth_date,
                                        description, profile_pic)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                     ''', (data['email'], data['username'], password_hash, data['name'], data['surname1'],
                           data.get('surname2', ''), data['birth_date'], data.get('description', ''), profile_pic))
        conn.commit()
        conn.close()
        # Modificamos el mensaje para que el usuario sepa qué ocurre
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