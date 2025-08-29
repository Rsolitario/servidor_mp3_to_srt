# generacion_subtitulos_inteligente.py

# Se comenta la línea original de whisper
# import whisper 
# Y se añade la importación de faster-whisper
from faster_whisper import WhisperModel

import srt
import datetime
import logging
import spacy
from typing import List, Dict, Any

# --- CONFIGURACIÓN DEL SISTEMA DE ÉNFASIS DINÁMICO ---

# 1. Umbral de Puntuación para Énfasis:
UMBRAL_DE_ENFASIS = 4.0

# 2. Máximo de palabras por grupo "normal"
MAX_PALABRAS_POR_GRUPO = 4

# 3. Pausa en segundos que fuerza la creación de un nuevo grupo
MAX_PAUSA_SEGUNDOS = 0.6

# 4. Puntuaciones para el análisis
PUNTOS_POR_TIPO_DE_PALABRA = {
    "NOUN": 2.0,   # Sustantivos (ej: casa, secreto)
    "PROPN": 2.5,  # Nombres Propios (ej: Google, María)
    "VERB": 1.5,   # Verbos (ej: correr, es)
    "ADJ": 1.5,    # Adjetivos (ej: grande, importante)
    "ADV": 1.0,    # Adverbios (ej: rápidamente)
}
PUNTOS_POR_PAUSA_LARGA = 2.5
PUNTOS_POR_DURACION_LARGA = 2.0


class DynamicSubtitleGeneratorFast:
    '''
    Tu control ahora reside en ajustar los parámetros de configuración al inicio del script:
    UMBRAL_DE_ENFASIS: Es tu perilla principal. ¿Quieres que el video sea más "frenético" con muchas palabras destacadas? Baja el umbral a 3.5. ¿Prefieres un estilo más tranquilo donde solo las palabras más importantes se destaquen? Súbelo a 4.5 o 5.0.
    MAX_PALABRAS_POR_GRUPO: Controla la longitud de tus frases normales.
    PUNTOS_POR_*: Para usuarios avanzados. Si crees que las pausas son más importantes que el tipo de palabra en tu estilo de habla, simplemente aumenta PUNTOS_POR_PAUSA_LARGA.
    '''
    def __init__(self, audio_path: str):
        self.audio_path = audio_path
        self.nlp_model = spacy.load("es_core_news_sm")
        self.all_words = self._transcribe_audio()
        if self.all_words:
            self._avg_word_duration = sum(w['end'] - w['start'] for w in self.all_words) / len(self.all_words)
        else:
            self._avg_word_duration = 0

    # --- MÉTODO MODIFICADO ---
    def _transcribe_audio(self) -> List[Dict[str, Any]]:
        """Transcribe el audio y devuelve una lista plana de palabras con timestamps usando faster-whisper."""
        try:
            # Se actualiza el mensaje de logging
            logging.info("Iniciando transcripción con Faster-Whisper...")
            
            # Se carga el modelo de faster-whisper optimizado para CPU.
            # "base" es el mismo tamaño que usabas.
            # compute_type="int8" ofrece una gran aceleración en CPU.
            model = WhisperModel("base", device="cpu", compute_type="int8")
            
            # La llamada a transcribe devuelve un generador de segmentos
            segments, info = model.transcribe(str(self.audio_path), word_timestamps=True, language="es")
            
            # Se necesita reconstruir la lista de palabras en el formato que el resto del código espera
            all_words = []
            for segment in segments:
                for word in segment.words:
                    all_words.append({
                        'word': word.word,
                        'start': word.start,
                        'end': word.end
                    })
            return all_words
            
        except Exception as e:
            # Se actualiza el mensaje de error
            logging.error(f"Error en la transcripción de Faster-Whisper: {e}", exc_info=True)
            return []
    # --- FIN DEL MÉTODO MODIFICADO ---

    def _calculate_emphasis_score(self, word_data: Dict, prev_word_data: Dict) -> float:
        """Calcula el puntaje de énfasis para una sola palabra."""
        score = 0.0
        
        # 1. Puntuación por Tipo de Palabra (Análisis Lingüístico)
        # Limpiamos la palabra antes de pasarla a spaCy por si tiene puntuación extraña
        cleaned_word = word_data['word'].strip()
        if not cleaned_word: return score # Si la palabra está vacía, no hay nada que hacer

        doc = self.nlp_model(cleaned_word)
        pos_tag = doc[0].pos_ if doc else ""
        score += PUNTOS_POR_TIPO_DE_PALABRA.get(pos_tag, 0.0)
        
        # 2. Puntuación por Pausa Previa (Análisis Prosódico)
        if prev_word_data:
            pause_before = word_data['start'] - prev_word_data['end']
            if pause_before > MAX_PAUSA_SEGUNDOS:
                score += PUNTOS_POR_PAUSA_LARGA

        # 3. Puntuación por Duración Larga (Análisis Prosódico)
        word_duration = word_data['end'] - word_data['start']
        # Una palabra es "larga" si dura un 75% más que el promedio
        if self._avg_word_duration > 0 and word_duration > self._avg_word_duration * 1.75:
            score += PUNTOS_POR_DURACION_LARGA
            
        return score

    def generate(self, srt_path: str) -> bool:
        """Genera y guarda el archivo SRT con subtítulos dinámicos."""
        if not self.all_words:
            logging.error("No hay palabras transcritas para procesar.")
            return False

        final_subtitles = []
        word_buffer = []

        def crear_subtitulo_desde_buffer(buffer):
            if not buffer: return
            content = " ".join(w['word'].strip() for w in buffer)
            sub = srt.Subtitle(
                index=len(final_subtitles) + 1,
                start=datetime.timedelta(seconds=buffer[0]['start']),
                end=datetime.timedelta(seconds=buffer[-1]['end']),
                content=content
            )
            final_subtitles.append(sub)

        for i, word_data in enumerate(self.all_words):
            prev_word = self.all_words[i-1] if i > 0 else None
            score = self._calculate_emphasis_score(word_data, prev_word)
            
            # Si la palabra supera el umbral de énfasis, trátala como especial
            if score >= UMBRAL_DE_ENFASIS:
                logging.info(f"Énfasis detectado! Palabra: '{word_data['word']}' (Puntaje: {score:.2f})")
                if word_buffer:
                    crear_subtitulo_desde_buffer(word_buffer)
                    word_buffer = []
                crear_subtitulo_desde_buffer([word_data])
                continue

            # La lógica de siempre para los grupos normales
            word_buffer.append(word_data)
            if len(word_buffer) >= MAX_PALABRAS_POR_GRUPO:
                crear_subtitulo_desde_buffer(word_buffer)
                word_buffer = []

        if word_buffer:
            crear_subtitulo_desde_buffer(word_buffer)
            
        srt_content = srt.compose(final_subtitles)
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)
        logging.info(f"Subtítulos inteligentes guardados en: {srt_path}")
        return True


# --- EJEMPLO DE USO ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    # ¡Recuerda cambiar esto por la ruta real de tu archivo de audio!
    AUDIO_FILE = "ruta/a/tu/audio.mp3" 
    OUTPUT_SRT_FILE = "subtitulos_inteligentes.srt"

    # 1. Crear una instancia del generador
    generator = DynamicSubtitleGeneratorFast(audio_path=AUDIO_FILE)
    
    # 2. Generar los subtítulos
    if generator.all_words:
        generator.generate(srt_path=OUTPUT_SRT_FILE)
    else:
        logging.error("No se pudo generar subtítulos porque la transcripción falló o devolvió una lista vacía.")