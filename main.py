import nextcord
from nextcord.ext import commands
from config import token

# client init
intents = nextcord.Intents.all()

activity = nextcord.Game(name="⑨Music⑨")
client = commands.AutoShardedBot(command_prefix='$', case_insensitive=True, activity=activity, intents=intents)

extensions = ['cogs.misc', 'cogs.pixiv', 'cogs.pidor', 'cogs.emotes', 'cogs.music_player', 'cogs.anime']

for extension in extensions:
    client.load_extension(extension)

client.run(token)
