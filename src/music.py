import yt_dlp as youtube_dl
import os, asyncio

class Music:
    YDL_OPTIONS = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
            }],
            'restrictfilenames': True,  # Évite les caractères spéciaux problématiques
            'noplaylist': True,
            'quiet': True,              # Réduit les logs dans la console
            }
    
    PATH = os.path.dirname(os.path.abspath(__file__))
    PATH_MP3= os.path.join(PATH, "music")

    @staticmethod # Indique que cette fonction ne prend ni 'self' ni 'cls'
    def sync_download(link_vid):
        """Fonction synchrone exécutée dans un thread séparé"""
        if not os.path.exists(Music.PATH_MP3):
            os.makedirs(Music.PATH_MP3)

        options = Music.YDL_OPTIONS.copy()
        options['outtmpl'] = os.path.join(Music.PATH_MP3, '%(title)s.%(ext)s')

        with youtube_dl.YoutubeDL(options) as ydl:
            info = ydl.extract_info(link_vid, download=True)
            temp_filename = ydl.prepare_filename(info)
            # On s'assure d'avoir l'extension .mp3 pour FFmpeg
            file_path = os.path.splitext(temp_filename)[0] + ".mp3"
            
            return info.get('title', 'Musique inconnue'), file_path

    @classmethod # Indique que le premier argument est la classe elle-même (cls)
    async def download(cls, url):
        """Méthode asynchrone appelée par le bot"""
        # On utilise cls.sync_download pour appeler la méthode de cette classe
        return await asyncio.to_thread(cls.sync_download, url)
