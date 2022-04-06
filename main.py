# import interactions
from config import token
from discord_slash import SlashCommand
from discord import Intents
from modules.discord_components import ComponentsBot

# client init
client = ComponentsBot(command_prefix='$', intents=Intents.default())
slash = SlashCommand(client, sync_commands=True)
# int_client = interactions.Client(token=token)

extensions = ['cogs.misc', 'cogs.pixiv', 'cogs.music_player', 'cogs.pidor', 'cogs.emotes', 'cogs.anime']

for extension in extensions:
    client.load_extension(extension)

# int_extensions = {'cogs.pixiv_interactions'}
#
# for int_extension in int_extensions:
#     int_client.load(int_extension)

# exec
client.run(token, bot=True)
# int_client.start()
