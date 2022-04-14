import pandas as pd
from nextcord import Embed, ChannelType
from time import sleep
from threading import *


class AnalysisModule:
    def __init__(self, client, db):
        self.discord_client = client
        self.voice_activity_collection = db["voice_activity"]
        self.messages_collection = db["messages"]
        self.voice_activity_thread = Thread(target=self.voice_activity_check)
        self.voice_activity_thread.start()
        self.db = db

    def __del__(self):
        self.voice_activity_collection.update_many({"session_ended": False}, {"$set": {"session_ended": True}})

    async def get_voice_activity(self, ctx):  # do after forming collection structure
        for item in self.voice_activity_collection.find({"guild_id": ctx.guild.id}):
            print(item)

        # answer = "```"
        # for activity in users_activity:
        #     answer += "#" + str(users_activity.index(activity) + 1) + " " + await self.fetch_user(activity["user_id"]) + " - " + str(round(activity["activity"], 2)) + "h" "\n"
        # answer += "```"

        # embed = Embed(title="Voice activity", description=answer)
        # await ctx.reply(embed=embed)

    def voice_activity_check(self):  # make adding new users to active list
        while True:
            active_users = self.get_active_voice_users()

            for item in self.voice_activity_collection.find({"session_ended": False}):
                if item["guild"] in active_users.keys() and item["user_id"] not in active_users[item["guild_id"]]:
                    self.voice_activity_collection.update_one({"_id": item["_id"]}, {"$set": {"session_ended": True}})

            for item in self.voice_activity_collection.find({"session_ended": False}):
                item["activity_minutes"] += 1

            sleep(60)

    def get_active_voice_users(self):
        active_users = {}
        for guild in self.discord_client.guilds:
            guild_active_users = []
            for channel in guild.channels:
                if channel.type == ChannelType.voice:
                    guild_active_users = channel.voice_states.keys()
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
            "attachments": ctx.attachments,
            "attachments_number": len(ctx.attachments)  # doesn't work
        }
        self.messages_collection.insert_one(new_item)

    async def get_userscores(self, ctx):
        df = pd.DataFrame(list(self.messages_collection.find({"guild_id": ctx.guild.id},
                                                             ["author_id", "content", "attachments_number"])))
        df["length"] = df["content"].apply(lambda x: len(x))
        df["score"] = df["length"] * 0.1 + df["attachments_number"] * 5
        df = df.groupby(["author_id"]).sum()

        answer = "```"
        for item in df:
            answer += "#" + str(df[df['author_id'] == item['author_id']].index[0]) + " - " + str(item["score"]) + "\n"
        answer = "```"
        embed = Embed(title="Top", description=answer)
        await ctx.reply(embed=embed)

    # async def fetch_user(self, id):
    #     user = await self.discord_client.fetch_user(id)
    #     return str(user.name) + "#" + str(user.discriminator)