import nextcord
from modules import logger as log
import logging
from nextcord.ext import commands

from config import TOKEN

log.init_logger()
logger = logging.getLogger(__name__)

# client init
intents = nextcord.Intents.all()

activity = nextcord.Game(name="⑨Music⑨")
client = commands.AutoShardedBot(command_prefix='$', case_insensitive=True,
                                 activity=activity, intents=intents)

extensions = ['cogs.pixiv', 'cogs.pidor', 'cogs.emotes',
              'cogs.music_player', 'cogs.anime', 'cogs.help',
              'cogs.cai', 'cogs.chatgpt']

for extension in extensions:
    client.load_extension(extension)

logger.info('Cogs initialized.')

client.run(TOKEN)
