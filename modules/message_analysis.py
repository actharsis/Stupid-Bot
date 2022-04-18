import pandas as pd
import asyncio
from nextcord import Embed, ChannelType


def time_to_str(time):
    return f"{int(time // 60)} h, {int(time % int(60))} min"


class AnalysisModule:
    def __init__(self, client, db):
        self.discord_client = client
        self.voice_activity_collection = db["voice_activity"]
        self.messages_collection = db["messages"]
        self.db = db
        client.loop.create_task(self.voice_activity_check())

    def __del__(self):
        self.voice_activity_collection.update_many({"session_ended": False}, {"$set": {"session_ended": True}})

    async def get_voice_activity(self, ctx):  # do after forming collection structure
        try:
            df = pd.DataFrame(list(self.voice_activity_collection.find({"guild_id": ctx.guild.id},
                                                                       ["user_id", "activity_minutes"])))
            df = df.sort_values("activity_minutes", ascending=False).head(10)
            df = df.reset_index()
            answer = "```"
            for item in df.itertuples():
                user = await self.discord_client.fetch_user(item.user_id)
                answer += f"#{str(item.Index + 1)} {user} - {time_to_str(item.activity_minutes)}\n"
            answer += "```"
            embed = Embed(title="Voice activity", description=answer)
        except KeyError:
            embed = Embed(title="Voice activity", description="Empty.")
        await ctx.send(embed=embed, ephemeral=True)

    async def voice_activity_check(self):  # make adding new users to active list
        while True:
            active_users = self.get_active_voice_users()

            for item in self.voice_activity_collection.find({"session_active": True}):
                guild_id = int(item["guild_id"])
                user = int(item["user_id"])
                if guild_id in active_users:
                    if user not in active_users[guild_id]:
                        self.voice_activity_collection.update_one({"_id": item["_id"]},
                                                                  {"$set": {"session_active": False}})
                    else:
                        self.voice_activity_collection.update_one({'_id': item['_id']},
                                                                  {'$inc': {'activity_minutes': 1}},
                                                                  upsert=False)
                        active_users[guild_id].pop(user)

            for guild_id in active_users:
                for uid, user in active_users[guild_id].items():
                    new_item = {
                        "guild_id": guild_id,
                        "user_id": uid,
                        "is_bot": user.bot,
                        "activity_minutes": 0,
                        "session_active": True
                    }
                    self.voice_activity_collection.insert_one(new_item)
            await asyncio.sleep(60)

    def get_active_voice_users(self):
        active_users = {}
        for guild in self.discord_client.guilds:
            guild_active_users = {}
            for channel in guild.channels:
                if channel.type == ChannelType.voice:
                    for user in channel.members:
                        guild_active_users[user.id] = user
            active_users[guild.id] = guild_active_users
        return active_users

    def save_message(self, ctx):
        new_item = {
            "guild_id": ctx.guild.id,
            "timestamp": ctx.created_at,
            "author_id": ctx.author.id,
            "is_bot": ctx.author.bot,
            "channel_id": ctx.channel.id,
            "content": ctx.content,
            "attachments_number": len(ctx.attachments)
        }
        self.messages_collection.insert_one(new_item)

    async def get_user_scores(self, ctx):
        try:
            df = pd.DataFrame(list(self.messages_collection.find({"guild_id": ctx.guild.id},
                                                                 ["author_id", "content", "attachments_number"])))
            df["length"] = df["content"].apply(lambda x: len(x))
            df["score"] = df["length"] * 0.1 + df["attachments_number"] * 5
            df = df.groupby(["author_id"]).sum().sort_values("score", ascending=False).head(10)
            df = df.reset_index()
            answer = "```"
            for item in df.itertuples():
                answer += f"#{str(item.Index + 1)} {await self.discord_client.fetch_user(item.author_id)} - " \
                          f"{str(int(item.score))}\n"

            answer += "```"
            embed = Embed(title="Top", description=answer)
        except KeyError:
            embed = Embed(title="Top", description="Empty.")
        await ctx.response.send_message(embed=embed, ephemeral=True)
