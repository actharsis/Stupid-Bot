import io
import urllib.parse

import aiohttp
import emoji
import interactions
import requests
from interactions import Embed, EmbedField, Extension, File


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


class Anime(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @interactions.extension_listener()
    async def on_message_reaction_add(self, reaction):
        channel = interactions.Channel(** await self.bot._http.get_channel(reaction.channel_id),
                                       _client=self.bot._http)
        message = await channel.get_message(reaction.message_id)
        try:
            demojized = emoji.demojize(reaction.emoji.name)
        except TypeError:
            demojized = None
        url = None
        if not message.author.bot and message.author != self.bot.me and demojized == ":red_question_mark:" and \
                message.attachments is not None and len(message.attachments) == 1:
            url = message.attachments[0].url
        if url is None:
            text = message.content.split()
            if text:
                text = text[0]
            if text.startswith('http'):
                url = text
        if url is not None:
            request = requests.get("https://api.trace.moe/search?cutBorders&url={}".
                                   format(urllib.parse.quote_plus(url))
                                   ).json()
            if request['result']:
                await self.bot._http.trigger_typing(reaction.channel_id)
                best = request['result'][0]
                info = anilist(best['anilist'])
                embed = Embed(title='Top Anime Result',
                              description=f"Best anime match: [**{info['data']['Media']['title']['english']}**]"
                                          f"(https://anilist.co/anime/{best['anilist']})")
                embed.fields = [
                    EmbedField(name="Episode", value=f"{best['episode']}", inline=True),
                    EmbedField(name="Time", value=f"{short_time(best['from'])}", inline=True),
                    EmbedField(name="Similarity", value=f"{int(best['similarity'] * 100)}%", inline=True)
                ]
                embed.set_thumbnail(url=info['data']['Media']['coverImage']['large'])
                await message.reply(embeds=embed)
                async with aiohttp.ClientSession() as session:
                    async with session.get(best['video']) as resp:
                        if resp.status == 200:
                            data = io.BytesIO(await resp.read())
                            await message.reply(files=File("cut.mp4", data))


def setup(bot):
    Anime(bot)
