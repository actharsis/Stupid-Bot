import discord

from discord.ext import commands
from config import settings
from discord_slash import SlashCommand

# client init
client = commands.Bot(command_prefix='$', intents=discord.Intents.all())
slash = SlashCommand(client, sync_commands=True)

initial_extensions = ['cogs.misc', 'cogs.pixiv', 'cogs.music_player', 'cogs.pidor']

for extension in initial_extensions:
    client.load_extension(extension)

# exec
client.run(settings['token'], bot=True)
