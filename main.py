import os
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import google.generativeai as genai
from tempfile import NamedTemporaryFile

# Configuración inicial de FastAPI
app = FastAPI(title="La Remera EC - Vision & Audio AI Engine")

# Configurar el SDK de Gemini usando la variable de entorno
# NOTA: Debes configurar GEMINI_API_KEY en las variables de entorno de Render
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ADVERTENCIA: No se encontró GEMINI_API_KEY. La API fallará en producción.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# Utilizamos gemini-flash-latest por defecto para máxima velocidad y capacidad multimodal
model = genai.GenerativeModel('gemini-flash-latest')

# Definimos la estructura del JSON que Make nos va a enviar
class MediaRequest(BaseModel):
    url: str
    media_type: str  # Esperamos que Make envíe "image" o "audio"

@app.post("/process-media")
async def process_media(request: MediaRequest):
    """
    Recibe una URL pública de GHL, descarga el archivo temporalmente,
    lo procesa con Gemini Flash y devuelve el texto limpio a Make.
    """
    temp_file_path = None
    gemini_file = None
    
    try:
        # 1. Descargar el archivo desde la URL que envía Make/GHL
        response = requests.get(request.url, timeout=10)
        response.raise_for_status()
        
        # 2. Configurar extensiones y MIME types según lo que pida Make
        if request.media_type.lower() == "image":
            suffix = ".jpg"
            mime_type = "image/jpeg"
            prompt = "Eres un asistente experto en camisetas de fútbol. Describe detalladamente la camiseta deportiva que ves en la imagen. Menciona el equipo o selección, el color principal, y si es posible, el año o temporada de la camiseta. Sé conciso."
        elif request.media_type.lower() == "audio":
            suffix = ".ogg"
            mime_type = "audio/ogg"
            prompt = "Transcribe exactamente lo que dice el cliente en este audio. Si está pidiendo un producto específico, haz un resumen de un párrafo al final indicando su intención."
        else:
            raise HTTPException(status_code=400, detail="media_type debe ser 'image' o 'audio'")

        # 3. Guardar el archivo temporalmente en el servidor
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        # 4. Subir el archivo a la API de Google (requerido para audios e imágenes grandes)
        gemini_file = genai.upload_file(path=temp_file_path, mime_type=mime_type)

        # 5. Generar el contenido con Gemini Flash
        result = model.generate_content([gemini_file, prompt])
        texto_generado = result.text

        # 6. Devolver el JSON limpio a Make
        return {"status": "success", "text": texto_generado}

    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"Error descargando el archivo: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando con Gemini: {str(e)}")
    
    finally:
        # 7. Limpieza absoluta: Borramos el archivo local y el de los servidores de Google
        if temp_file_path and os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        if gemini_file:
            try:
                genai.delete_file(gemini_file.name)
            except Exception as e:
                print(f"Error limpiando archivo de Gemini: {e}")

# Endpoint de prueba para saber si el servidor está vivo
@app.api_route("/", methods=["GET", "HEAD"])
def read_root():
    return {"status": "Motor de IA en línea y operativo."}