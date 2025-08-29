# ==============================================================================
# PASO 1: INSTALACIÓN Y CONFIGURACIÓN
# ==============================================================================
print("Paso 1: Instalando librerías necesarias...")
!pip install flask pycloudflared openai-whisper ffmpeg-python --quiet

import os
import threading
import logging
import uuid
from flask import Flask, request, jsonify, send_from_directory, url_for
from pycloudflared import try_cloudflare
from generacion_subtitulos_fast import DynamicSubtitleGeneratorFast
from werkzeug.utils import secure_filename

tasks = {}
UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)
app = Flask(__name__)
PORT = 5000

# ==============================================================================
# PASO 2: LÓGICA DE PROCESAMIENTO (AHORA AISLADA Y CORREGIDA)
# ==============================================================================
def process_video_in_background(task_id: str, video_path: str, srt_path: str, srt_filename: str):
    global tasks
    # --- INICIO DE LA CORRECCIÓN: Sintaxis de Python con indentación ---
    try:
        print(f"[{task_id}] Hilo iniciado. Cargando modelo para: {video_path}")
        tasks[task_id]['status'] = 'processing'
        
        # Esta es la operación lenta que ahora está completamente aislada
        generator = DynamicSubtitleGeneratorFast(audio_path=video_path)
        
        print(f"[{task_id}] Modelo cargado. Generando subtítulos...")
        if generator.all_words:
            generator.generate(srt_path=srt_path)
        else:
            raise RuntimeError("La transcripción no produjo resultados.")
        
        print(f"[{task_id}] Transcripción completada.")
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['result_filename'] = srt_filename
        
    except Exception as e:
        print(f"[{task_id}] Ha ocurrido un error: {e}")
        tasks[task_id]['status'] = 'failed'
        tasks[task_id]['error'] = str(e)
        
    finally:
        # Es importante no borrar el archivo original hasta que el SRT esté generado
        # Si la tarea falla, quizás quieras inspeccionar el archivo de video
        if os.path.exists(video_path):
            os.remove(video_path)
            print(f"[{task_id}] Archivo de video de origen eliminado.")
    # --- FIN DE LA CORRECCIÓN ---

# ==============================================================================
# PASO 3: NUEVAS RUTAS DE LA API
# ==============================================================================

# ENDPOINT 1: Solo para subir el archivo. Debe ser rápido.
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'video' not in request.files:
        return jsonify({"error": "No se encontró el archivo de video"}), 400
    
    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({"error": "No se seleccionó ningún archivo"}), 400

    # Genera un nombre de archivo único para evitar conflictos
    original_filename = secure_filename(video_file.filename)
    extension = os.path.splitext(original_filename)[1]
    unique_filename = f"{uuid.uuid4()}{extension}"
    
    video_path = os.path.join(UPLOAD_FOLDER, unique_filename)
    video_file.save(video_path) # Esta es la única operación que realiza

    print(f"Archivo '{original_filename}' guardado como '{unique_filename}'")

    return jsonify({
        "message": "Archivo subido exitosamente.",
        "uploaded_filename": unique_filename
    })

# ENDPOINT 2: Para iniciar el procesamiento de un archivo ya subido. Instantáneo.
@app.route('/process', methods=['POST'])
def process_file():
    data = request.get_json()
    if not data or 'filename' not in data:
        return jsonify({"error": "Se requiere el 'filename' del archivo subido."}), 400

    unique_filename = data['filename']
    video_path = os.path.join(UPLOAD_FOLDER, unique_filename)

    if not os.path.exists(video_path):
        return jsonify({"error": f"Archivo no encontrado: {unique_filename}"}), 404

    srt_filename = f"{os.path.splitext(unique_filename)[0]}.srt"
    srt_path = os.path.join(RESULT_FOLDER, srt_filename)
    
    task_id = str(uuid.uuid4())
    tasks[task_id] = {'status': 'pending', 'source_filename': unique_filename}

    background_thread = threading.Thread(
        target=process_video_in_background,
        args=(task_id, video_path, srt_path, srt_filename)
    )
    background_thread.start()

    status_url = url_for('get_task_status', task_id=task_id, _external=True)
    return jsonify({
        "message": "El procesamiento ha comenzado.",
        "task_id": task_id,
        "status_url": status_url
    }), 202

# ENDPOINT 3: Para consultar el estado (sin cambios)
@app.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "ID de tarea no encontrado"}), 404
    
    response = task.copy()
    if response.get('status') == 'completed':
        response['download_url'] = url_for('download_srt', filename=task['result_filename'], _external=True)
        
    return jsonify(response)

@app.route('/download/<filename>', methods=['GET'])
def download_srt(filename):
    return send_from_directory(RESULT_FOLDER, filename, as_attachment=True)

# ==============================================================================
# PASO 4: INICIAR EL SERVIDOR (SIN CAMBIOS)
# ==============================================================================
flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=PORT, debug=False))
flask_thread.daemon = True
flask_thread.start()

public_url = try_cloudflare(port=PORT)
print(f"✅ Servidor iniciado. Tu API está disponible públicamente en: {public_url}")