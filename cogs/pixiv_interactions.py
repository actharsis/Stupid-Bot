import interactions
from config import use_selenium
from discord.colour import Colour
from interactions import Extension, Embed
from modules.pixiv_auth import selenium_login
from cogs.pixiv import BetterAppPixivAPI


class PixivInt(Extension):
    def __init__(self, bot: interactions.Client):
        self.bot = bot

    @interactions.extension_command(name="pixiv_token", description="Log in to Pixiv via refresh token",
                                    options=[
                                        interactions.Option(
                                            name="token",
                                            description="Your pixiv login",
                                            type=interactions.OptionType.STRING,
                                            required=True,
                                        )
                                    ])
    async def pixiv_token(self, ctx, token):
        await ctx.defer()
        try:
            a = BetterAppPixivAPI(token=token)
            server = str(ctx.guild.id)
            api = a
            tokens = {"value": token, "time": str(0)}
            embed = Embed(title="Successfully logged in :)", color=Colour.green())
        except:
            embed = Embed(title="Can't login with given token :(", color=Colour.red())
        await ctx.send(embed=embed, delete_after=10.0)

    if use_selenium:
        @interactions.extension_command(name="pixiv_login", description="Log in to Pixiv",
                                        options=[
                                            interactions.Option(
                                                name="login",
                                                description="Your pixiv login",
                                                type=interactions.OptionType.STRING,
                                                required=True,
                                            ),
                                            interactions.Option(
                                                name="password",
                                                description="Your pixiv password",
                                                type=interactions.OptionType.STRING,
                                                required=True,
                                            )
                                        ])
        async def pixiv_login(self, ctx, login, password):
            await ctx.defer()
            try:
                token = await selenium_login(login, password)
                if token is None:
                    await ctx.send(embeds=Embed(title="Can't log in. Captcha required :(\n"
                                                     "Try pixiv token instead",
                                               color=Colour.red()),
                                   delete_after=10.0)
                    return
                a = BetterAppPixivAPI(token=token)
                server = str(ctx.guild.id)
                api = a
                tokens = {"value": token, "time": str(0)}
                embed = Embed(title="Successfully logged in :)", color=Colour.green())
            except:
                embed = Embed(title="Can't log in with given token :(", color=Colour.red())
            await ctx.send(embed=embed, delete_after=10.0)


def setup(bot):
    PixivInt(bot)
