settings = {
    'token': ''
}

song_cache = "song_cache.mp3"

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'outtmpl': song_cache,
    'noplaylist': True
}
