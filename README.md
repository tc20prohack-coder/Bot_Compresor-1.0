# MediaShaper Alternative — Telegram Bot

Bot multimedia para Telegram, implementado en Python con Pyrogram, FFmpeg, Pillow, pypdf y LibreOffice.

## Incluye
- Vídeo: compresión H.264, conversión MP4/MKV/GIF, escalado 1080p/720p/480p y extracción de audio.
- Audio: MP3/WAV/OGG/M4A y bitrate MP3 128/192/320 kbps.
- Imágenes: JPG/PNG/WebP/AVIF, reducción de tamaño y limpieza de metadatos EXIF.
- Documentos: PDF y conversión Office a PDF mediante LibreOffice.
- Stickers: WebP estático y WebM desde vídeo/GIF.
- ZIP/TAR: extracción segura y procesamiento por lotes básico.
- Historial, créditos internos, administración, progreso y cancelación.
- Endpoint HTTP `/health` para Render.

## Requisitos
Python 3.11, FFmpeg y LibreOffice (este último para conversiones Office).

## Configuración local
1. Copia `.env.example` a `.env`.
2. Completa `BOT_TOKEN`, `API_ID`, `API_HASH` y `ADMIN_IDS`.
3. Instala dependencias: `pip install -r requirements.txt`.
4. Instala FFmpeg y LibreOffice en el sistema.
5. Ejecuta `python bot.py`.

## Render
1. Sube todo el proyecto a un repositorio GitHub.
2. En Render elige **New + > Blueprint** y conecta el repositorio (usa `render.yaml`).
3. Completa las variables secretas `BOT_TOKEN`, `API_ID`, `API_HASH` y `ADMIN_IDS`.
4. Despliega el servicio.
5. Comprueba `https://TU-SERVICIO.onrender.com/health`.

El proyecto usa Docker para instalar FFmpeg y LibreOffice. El disco persistente se monta en `/var/data` para SQLite. Los archivos de trabajo se guardan temporalmente en `/tmp` y se eliminan al terminar.

## Comandos
- `/start`
- `/help`
- `/balance`
- `/history`
- `/buy`
- `/cancel`
- `/addcredits USER_ID CANTIDAD` (administrador)
- `/stats` (administrador)

## Límites y notas
- `MAX_FILE_MB` limita el tamaño de entrada descargable por el bot.
- Los bots de Telegram tienen límites de descarga/subida que dependen del método y del servidor/API. El límite configurado aquí no garantiza que Telegram permita transferir todos los archivos hasta ese tamaño.
- Los créditos son internos. No se ha integrado una pasarela de pago.
- La compresión de PDF con pypdf reescribe el documento, pero no garantiza una reducción sustancial del tamaño.
- Las conversiones Office requieren LibreOffice.
- AVIF requiere soporte AVIF en la compilación de Pillow instalada.
- No hay separación de voz/instrumental, subtitulado automático ni integración oficial para publicar paquetes de stickers en Telegram en esta primera versión.
- Render debe ejecutar un único proceso/instancia de este bot por token. No escales horizontalmente sin implementar bloqueo distribuido.
- Para ejecución continua, utiliza un servicio Render que no entre en suspensión. Los servicios gratuitos pueden suspenderse y no son adecuados para bots que deban permanecer disponibles 24/7.

## Seguridad
Nunca subas `.env` al repositorio. Usa las variables secretas de Render. Configura `ADMIN_IDS` con IDs numéricos de Telegram, separados por comas.
