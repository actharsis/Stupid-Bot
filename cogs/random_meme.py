import asyncio
import contextlib
import random

from nextcord.ext import commands
import nextcord
from modules import wavelink


async def play_stuff(vc):
    player = await vc.connect(cls=wavelink.Player)
    playlist = await wavelink.YouTubePlaylist.search(
        query="https://www.youtube.com/playlist?list=PL1a0PDpxbrUovTamizbBZqWgfw5u-X2h_"
    )
    amount = len(playlist.tracks)
    idx = random.randrange(amount)
    track = playlist.tracks[idx]
    await player.play(track)


class RandomMeme(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(bot=self.bot,
                                            host='127.0.0.1',
                                            port=2333,
                                            password='youwillpass')

    @commands.Cog.listener()
    async def on_ready(self):
        while True:
            await asyncio.sleep(300)
            with contextlib.suppress(Exception):
                for guild in self.bot.guilds:
                    start = random.randrange(4)
                    if start == 0:
                        channels = guild.channels
                        best_channel = None
                        max_people = 0
                        for channel in channels:
                            if isinstance(channel, nextcord.VoiceChannel):
                                c = self.bot.get_channel(channel.id)
                                people = len(c.members)
                                if people > max_people:
                                    max_people = people
                                    best_channel = c
                        if best_channel is not None:
                            await play_stuff(best_channel)

    @commands.Cog.listener()
    async def on_wavelink_track_end(
            self, player: wavelink.player, track: wavelink.Track, reason):
        await player.disconnect()


def setup(bot):
    bot.add_cog(RandomMeme(bot))
