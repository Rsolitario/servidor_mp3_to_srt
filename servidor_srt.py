# ==============================================================================
# PASO 1: INSTALACIÓN Y CONFIGURACIÓN DEL ENTORNO
# ==============================================================================
print("Paso 1: Instalando librerías necesarias...")
!pip install flask flask-ngrok pyngrok --quiet

import os
import time
import threading
from flask import Flask, request, jsonify, send_from_directory
from pyngrok import ngrok
from generacion_subtitulos_fast import DynamicSubtitleGeneratorFast
import logging

# --- Configuración de ngrok (MUY RECOMENDADO) ---
# Ve a https://dashboard.ngrok.com/get-started/your-authtoken
# Copia tu token y pégalo aquí para evitar límites de tiempo.
NGROK_AUTH_TOKEN = ""  # PEGA TU TOKEN DE NGROK AQUÍ. EJ: "2Duw...xyz"

if NGROK_AUTH_TOKEN:
    ngrok.set_auth_token(NGROK_AUTH_TOKEN)
    print("Token de ngrok configurado exitosamente.")
else:
    print("ADVERTENCIA: No se ha configurado un token de ngrok. La sesión puede expirar pronto.")

# --- Configuración de Flask ---
UPLOAD_FOLDER = 'uploads'
RESULT_FOLDER = 'results'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULT_FOLDER, exist_ok=True)

app = Flask(__name__)
PORT = 5000 # Flask se ejecutará en el puerto 5000

# ==============================================================================
# PASO 2: TU LÓGICA DE PROCESAMIENTO (PLACEHOLDER)
# ==============================================================================
def generar_srt_desde_video(AUDIO_FILE: str, srt_path: str) -> None:
    """
    PLACEHOLDER: Inserta tu lógica de generación de SRT aquí.
    Esta función se ejecutará dentro del entorno de Colab.
    """
    generator = DynamicSubtitleGeneratorFast(audio_path=AUDIO_FILE)
    # 2. Generar los subtítulos
    if generator.all_words:
        generator.generate(srt_path=srt_path)
    else:
        logging.error("No se pudo generar subtítulos porque la transcripción falló o devolvió una lista vacía.")


# ==============================================================================
# PASO 3: RUTAS DE LA API FLASK (EL CÓDIGO DEL SERVIDOR)
# ==============================================================================
@app.route('/upload', methods=['POST'])
def upload_and_process_video():
    if 'video' not in request.files:
        return jsonify({"error": "No se encontró el archivo de video"}), 400
    
    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({"error": "No se seleccionó ningún archivo"}), 400

    video_path = os.path.join(UPLOAD_FOLDER, video_file.filename)
    video_file.save(video_path)

    srt_filename = f"{os.path.splitext(video_file.filename)[0]}.srt"
    srt_path = os.path.join(RESULT_FOLDER, srt_filename)

    try:
        generar_srt_desde_video(video_path, srt_path)
    except Exception as e:
        return jsonify({"error": f"Falló el procesamiento del video: {e}"}), 500
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

    # Devuelve la URL pública completa para la descarga
    public_url = ngrok.get_tunnels()[0].public_url
    return jsonify({
        "message": "Procesamiento completado.",
        "download_url": f"{public_url}/download/{srt_filename}"
    })

@app.route('/download/<filename>', methods=['GET'])
def download_srt(filename):
    return send_from_directory(RESULT_FOLDER, filename, as_attachment=True)

@app.route('/')
def index():
    public_url = ngrok.get_tunnels()[0].public_url
    return f"Servidor Flask funcionando en Colab. Acceso público en: {public_url}"

# ==============================================================================
# PASO 4: INICIAR EL SERVIDOR Y EL TÚNEL DE NGROK
# ==============================================================================
def run_app():
  # Inicia Flask en un hilo separado para no bloquear la ejecución de la celda
  flask_thread = threading.Thread(target=app.run, kwargs={'host': '0.0.0.0', 'port': PORT})
  flask_thread.daemon = True
  flask_thread.start()

# Abre un túnel HTTP al puerto en el que se ejecuta Flask
public_url = ngrok.connect(PORT)
print(f"✅ Servidor iniciado. Tu API está disponible públicamente en: {public_url}")

# Ejecutamos la app (esto mantendrá la celda activa)
run_app()
# NOTA: La celda se quedará ejecutándose. Esto es normal.
# Para detener el servidor, interrumpe la ejecución de la celda.
