import pymongo
from config import settings
from discord_slash import SlashCommand
from discord.ext.commands import Bot
from discord import Intents

# client init
client = Bot(command_prefix='$', intents=Intents.all())
slash = SlashCommand(client, sync_commands=True)

db_client = pymongo.MongoClient(settings['DBAddress'])
db = db_client['TabaBotDB']

initial_extensions = ['cogs.misc', 'cogs.pixiv', 'cogs.music_player', 'cogs.pidor', 'cogs.emotes', 'cogs.anime']

for extension in initial_extensions:
    client.load_extension(extension)

# exec
client.run(settings['token'], bot=True)
