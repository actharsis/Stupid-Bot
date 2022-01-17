settings = {
    'token': ''
}

pixiv_refresh_token = ''
pixiv_show_embed_illust = False

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'mp3',
        'preferredquality': '192',
    }],
    'noplaylist': True
}
