import aiohttp
import io
import emoji
import requests
import urllib.parse

from PIL import Image
from nextcord import Embed, File
from nextcord.ext import commands
from saucenao_api import AIOSauceNao
from config import saucenao_token, safety

if safety:
    from modules.predict import is_nsfw


def anilist(idx):
    query = '''
    query ($id: Int) { # Define which variables will be used in the query (id)
      Media (id: $id, type: ANIME) {
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


def get_url(message):
    url = None
    if message.attachments is not None and len(message.attachments) == 1:
        url = message.attachments[0].url
    if url is None:
        text = message.content.split()
        if text:
            text = text[0]
        else:
            return
        if text.startswith('http'):
            url = text
    return url


async def send_trace_moe(message, trace, characters=None):
    info = anilist(trace['anilist'])
    title = info['data']['Media']['title']['english']
    if title is None:
        title = info['data']['Media']['title']['native']
    embed = Embed(title='Top Anime Result',
                  description=f"Best anime match: [**{title}**]"
                              f"(https://anilist.co/anime/{trace['anilist']})")
    embed.add_field(name="Episode",
                    value=f"{trace['episode'] if trace['episode'] is not None else '1'}",
                    inline=True)
    embed.add_field(name="Time", value=f"{short_time(trace['from'])}", inline=True)
    embed.add_field(name="Similarity", value=f"{int(trace['similarity'] * 100)}%", inline=True)
    if characters is not None and len(characters) > 0:
        embed.add_field(name="Characters:", value=characters, inline=False)
    thumbnail = info['data']['Media']['coverImage']['large']
    if safety and is_nsfw(thumbnail) and not message.channel.nsfw:
        await message.reply(embed=embed)
        return
    embed.set_thumbnail(url=thumbnail)
    await message.reply(embed=embed)
    async with aiohttp.ClientSession() as session:
        async with session.get(trace['video']) as resp:
            if resp.status == 200:
                data = io.BytesIO(await resp.read())
                await message.reply(file=File(data, "cut.mp4"))


async def send_sauce_nao(message, sauce, characters=None):
    title = f"**{sauce.title}**"
    if sauce.urls:
        title = f"[{title}]({sauce.urls[0]})"
    embed = Embed(title='Top SauceNAO Result',
                  description=f"Best match: {title}")
    resource = sauce.index_name.split(':')[1].split('-')[0].rstrip()
    embed.add_field(name="Found in:", value=f"{resource}", inline=True)
    if sauce.index_id == 5:
        embed.add_field(name="Pixiv ID:", value=f"{sauce.raw['data']['pixiv_id']}", inline=True)
    embed.add_field(name="Similarity:", value=f"{sauce.similarity}%", inline=True)
    if characters is not None and len(characters) > 0:
        embed.add_field(name="Characters:", value=characters, inline=False)
    if safety and is_nsfw(sauce.thumbnail) and not message.channel.nsfw:
        await message.reply(embed=embed)
        return
    embed.set_thumbnail(url=sauce.thumbnail)
    await message.reply(embed=embed)


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

        if not message.author.bot and message.author.id == payload.user_id and demojized == ":red_question_mark:":
            url = get_url(message)
            if url is not None:
                trace = requests.get("https://api.trace.moe/search?cutBorders&url={}".
                                     format(urllib.parse.quote_plus(url))
                                     ).json()['result'][0]
                try:
                    tr_sim = int(trace['similarity'] * 100)
                except KeyError:
                    tr_sim = 0
                response = requests.get(url)
                with io.BytesIO(response.content) as img_bytes:
                    image = Image.open(img_bytes)
                    if image.width < image.height:
                        tr_sim = 0
                if tr_sim < 88:
                    tr_sim = 0

                sauce = None
                characters = None
                try:
                    sauce = await AIOSauceNao(saucenao_token).from_url(url)
                    best = None
                    for i, item in enumerate(sauce.results):
                        if sauce.results[0].similarity - item.similarity < 4 and item.index_id == 5 and best is None:
                            best = i
                        if 'characters' in item.raw['data'] and characters is None:
                            characters = item.raw['data']['characters']
                    if best is None:
                        best = 0
                    sauce = sauce.results[best]
                    snao_sim = sauce.similarity
                except:
                    snao_sim = 0

                if max(tr_sim, snao_sim) < 55:
                    await message.reply(embed=Embed(title='idk :('), delete_after=5)
                    return

                await channel.trigger_typing()
                if tr_sim - snao_sim > -2:
                    await send_trace_moe(message, trace, characters)
                else:
                    await send_sauce_nao(message, sauce, characters)


def setup(bot):
    bot.add_cog(Anime(bot))
