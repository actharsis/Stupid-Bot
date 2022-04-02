import aiohttp
import discord
import io

import emoji
import requests
import urllib.parse

from discord import Embed
from discord.ext import commands


def anilist(idx):
    query = '''
    query ($id: Int) { # Define which variables will be used in the query (id)
      Media (id: $id, type: ANIME) { # Insert our variables into the query arguments (id) (type: ANIME is hard-coded in the query)
        id
        title {
          romaji
          english
          native
        }
        coverImage {
          large
        }
      }
    }
    '''
    variables = {
        'id': idx
    }
    url = 'https://graphql.anilist.co'
    response = requests.post(url, json={'query': query, 'variables': variables})
    return response.json()


def short_time(time):
    return f"{int(time // 60)}:{int(time % int(60))}"


class Anime(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        channel = self.bot.get_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        try:
            demojized = emoji.demojize(payload.emoji.name)
        except TypeError:
            demojized = None
        if message.author != self.bot.user and demojized == ":red_question_mark:" and \
                message.attachments is not None and len(message.attachments) == 1:
            request = requests.get("https://api.trace.moe/search?cutBorders&url={}".
                                   format(urllib.parse.quote_plus(message.attachments[0].url))
                                   ).json()
            print(request)
            if request['result']:
                await channel.trigger_typing()
                best = request['result'][0]
                info = anilist(best['anilist'])
                embed = Embed(title='Top Anime Result',
                              description=f"Best match anime [**{info['data']['Media']['title']['english']}**]"
                                          f"(https://anilist.co/anime/{best['anilist']})")
                embed.add_field(name="Episode", value=f"{best['episode']}", inline=True)
                embed.add_field(name="Time", value=f"{short_time(best['from'])}", inline=True)
                embed.add_field(name="Similarity", value=f"{int(best['similarity'] * 100)}%", inline=True)
                embed.set_image(url=best['image'])
                embed.set_thumbnail(url=info['data']['Media']['coverImage']['large'])
                await message.reply(embed=embed)
                async with aiohttp.ClientSession() as session:
                    async with session.get(best['video']) as resp:
                        if resp.status == 200:
                            data = io.BytesIO(await resp.read())
                            await message.reply(file=discord.File(data, "cut.mp4"))


def setup(bot):
    bot.add_cog(Anime(bot))
