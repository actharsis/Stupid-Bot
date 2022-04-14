import aiohttp
import io

import emoji
import requests
import urllib.parse

from nextcord import Embed, File
from nextcord.ext import commands
from saucenao_api import AIOSauceNao
from config import saucenao_token


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
        url = None
        if not message.author.bot and message.author != self.bot.user and demojized == ":red_question_mark:" and \
                message.attachments is not None and len(message.attachments) == 1:
            url = message.attachments[0].url
        if url is None:
            text = message.content.split()
            if text:
                text = text[0]
            else:
                return
            if text.startswith('http'):
                url = text
        if url is not None:
            request = requests.get("https://api.trace.moe/search?cutBorders&url={}".
                                   format(urllib.parse.quote_plus(url))
                                   ).json()
            sauce = None
            try:
                sauce = await AIOSauceNao(saucenao_token).from_url(url)
                best = 0
                for i, item in enumerate(sauce.results):
                    if sauce.results[0].similarity - item.similarity < 4 and item.index_id == 5:
                        best = i
                sauce = sauce.results[best]
                snao_sim = sauce.similarity
            except:
                snao_sim = 0
            try:
                tr_sim = int(request['result'][0]['similarity'] * 100)
            except:
                tr_sim = 0
            if max(tr_sim, snao_sim) < 82:
                await message.reply(embed=Embed(title='idk :('), delete_after=5)
                return

            await channel.trigger_typing()
            if tr_sim - snao_sim > -2:
                best = request['result'][0]
                info = anilist(best['anilist'])
                embed = Embed(title='Top Anime Result',
                              description=f"Best anime match: [**{info['data']['Media']['title']['english']}**]"
                                          f"(https://anilist.co/anime/{best['anilist']})")
                embed.add_field(name="Episode", value=f"{best['episode']}", inline=True)
                embed.add_field(name="Time", value=f"{short_time(best['from'])}", inline=True)
                embed.add_field(name="Similarity", value=f"{int(best['similarity'] * 100)}%", inline=True)
                embed.set_thumbnail(url=info['data']['Media']['coverImage']['large'])
                await message.reply(embed=embed)
                async with aiohttp.ClientSession() as session:
                    async with session.get(best['video']) as resp:
                        if resp.status == 200:
                            data = io.BytesIO(await resp.read())
                            await message.reply(file=File(data, "cut.mp4"))
            else:
                embed = Embed(title='Top SauceNAO Result',
                              description=f"Best match: [**{sauce.title}**]"
                                          f"({sauce.urls[0]})")
                resource = sauce.index_name.split(':')[1].split('-')[0].rstrip()
                embed.add_field(name="Found in:", value=f"{resource}", inline=True)
                if sauce.index_id == 5:
                    embed.add_field(name="Pixiv ID", value=f"{sauce.raw['data']['pixiv_id']}", inline=True)
                embed.add_field(name="Similarity", value=f"{sauce.similarity}%", inline=True)
                embed.set_thumbnail(url=sauce.thumbnail)
                await message.reply(embed=embed)


def setup(bot):
    bot.add_cog(Anime(bot))
