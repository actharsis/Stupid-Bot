import json
import nextcord

from nextcord import Embed, SlashOption, slash_command
from nextcord.colour import Colour
from nextcord.ext import commands


def mimic(ctx, text):
    resend = False
    user = ctx.author
    ar = text.split()
    if len(ar) < 2:
        return text, user, resend
    pref = ar[0]
    if pref != "mimicry":
        return text, user, resend
    call = ar[1]
    if call[2] == '!':
        call = call[:2] + call[3:]
    for member in ctx.guild.members:
        mention = member.mention
        if mention[2] == '!':
            mention = mention[:2] + mention[3:]
        if call == mention or call == str(member.id):
            user = member
            resend = True
            text = text[len(pref) + len(call) + 2:]
            break
    return text, user, resend


class EmotesCog(commands.Cog, name="Emotes"):
    """
    **Emotes cog** - allows you to use reactions that require a discord nitro subscription.

    Technically, it just replace your message with a webhook that impersonates you
    if your message contain a reaction that need a subscription.

    To make it work, you need to /subscribe to be replaced by a bot when needed.

    Use /add to add specific reaction in bot DB. It's not gonna work without that.

    For non-nitro users:
    Copy link of needed emoji, then take it's id
    For example:
    https://cdn.discordapp.com/emojis/262941483232002048.webp?size=128&quality=lossless
    Id of this emoji is **262941483232002048**
    Then build a valid emoji by mask
    ***<:emoji_name:emoji_id>*** - if it is a static emoji
    ***<a:emoji_name:emoji_id>*** - if it's an animated emoji
    For the same example, proper add usage:
    /add emoji:<:cirno_blush:262941483232002048>

    ***Available commands***:
    **/subscribe** - make this feature enabled for you
    **/add** - add emoji to the DB

    You also can try typing 'mimicry user_id text' to do nasty things with this cog...
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reactions = {}
        self.sub_users = set()
        self.load()

    async def act(self, ctx, member: nextcord.Member, *, message=None):
        if message is None:
            await ctx.send(f'No message provided', delete_after=10.0)
            return
        name = member.nick
        if name is None:
            name = member.name
        webhook = await ctx.channel.create_webhook(name=name)
        self.bot.loop.create_task(ctx.delete())
        await webhook.send(str(message), username=name, avatar_url=member.avatar.url)
        webhooks = await ctx.channel.webhooks()
        for webhook in webhooks:
            await webhook.delete()

    def save(self, users=False, emoji=False):
        if users:
            with open('json/emoji_users.json', 'w') as file:
                file.write(json.dumps(list(self.sub_users)))
        if emoji:
            with open('json/emoji_list.json', 'w') as file:
                file.write(json.dumps(self.reactions))

    def load(self):
        try:
            with open('json/emoji_users.json', 'r') as file:
                self.sub_users = set(json.load(file))
            with open('json/emoji_list.json', 'r') as file:
                self.reactions = json.load(file)
        except:
            pass

    @commands.Cog.listener()
    async def on_ready(self):
        # await self.load_emotes()
        pass

    @commands.Cog.listener()
    async def on_message(self, ctx):
        if not ctx.author.bot and len(ctx.content) > 0:
            text, user, resend_mimic = mimic(ctx, ctx.content)
            text, resend_emote = self.parse_emotes(text)
            if str(ctx.author.id) not in self.sub_users:
                resend_emote = False
            if resend_mimic or resend_emote:
                await self.act(ctx, user, message=text)

    async def load_emotes(self):
        for guild in self.bot.guilds:
            for emoji in guild.emojis:
                self.reactions[f":{emoji.name}:"] = str(emoji)

    def parse_emotes(self, text):
        changed = False
        new_text = ""
        word = []
        pc = ' '
        for c in text:
            if c == ':' and pc in [' ', '\n']:
                word += c
            elif c == ':' and len(word) > 0:  # we found a reaction
                word += c
                str_word = ''.join(map(str, word))
                if str_word in self.reactions.keys():
                    changed = True
                    new_text += self.reactions[str_word]
                else:
                    new_text += str_word
                word.clear()
            elif (c.isalnum() or c in ['-', '_']) and len(word) > 0:
                word += c
            else:
                if len(word):
                    new_text += ''.join(map(str, word))
                new_text += c
                word.clear()
            pc = c
        return new_text, changed

    @slash_command(name='subscribe', description='Subscribe/unsubscribe from emoji replacing feature')
    async def subscribe(self, ctx):
        await ctx.response.defer()
        user_id = str(ctx.user.id)
        if user_id in self.sub_users:
            embed = Embed(title="You've been deleted from list", color=Colour.red())
            self.sub_users.remove(user_id)
        else:
            embed = Embed(title="You have been added to the list", color=Colour.green())
            self.sub_users.add(user_id)
        self.save(users=True)
        await ctx.send(embed=embed, delete_after=10.0)

    @slash_command(name='add', description='Add/remove emoji')
    async def add(self, ctx, emoji: str = SlashOption(name="emoji",
                                                      description="Your emoji",
                                                      required=True)):
        ar = emoji.split(':')
        if len(ar) == 3 and len(emoji) > 4 and emoji[0] == '<' and \
                (emoji[1] == ':' or emoji[1] == 'a' and emoji[2] == ':') and emoji[-1] == '>':
            name = f":{ar[1]}:"
            if name not in self.reactions:
                self.reactions[name] = emoji
                embed = Embed(title="Emoji added :)", color=Colour.green())
            elif self.reactions[name] != emoji:
                self.reactions[name] = emoji
                embed = Embed(title="Emoji replaced", color=Colour.green())
            else:
                self.reactions.pop(name)
                embed = Embed(title="Emoji deleted", color=Colour.green())
            self.save(emoji=True)
        else:
            embed = Embed(title="Wrong emoji :(", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)


def setup(bot):
    bot.add_cog(EmotesCog(bot))
