import models
from discord import Embed
from time import sleep
from discord import ChannelType
from threading import *
from main import db

class Analysis_module:
    def __init__(self, client):
        self.discord_client = client
        self.voice_activity_collection = db['voice_activity']
        self.messages_collection = db['messages']
        self.voice_activity_thread = Thread(target = self.voice_activity_check)
        self.voice_activity_thread.start()

    def __del__(self):
        self.voice_activity_collection.update_many({'session_ended': False}, {'$set' : {'session_ended' : True}})

    async def get_voice_activity(self, ctx): #do after forming collection structure
        for item in self.voice_activity_collection.find({'guild_id': ctx.guild.id}):
            print(item)

        # answer = '```'
        # for activity in users_activity:
        #     answer += '#' + str(users_activity.index(activity) + 1) + ' ' + await self.fetch_user(activity['user_id']) + ' - ' + str(round(activity['activity'], 2)) + 'h' '\n'
        # answer += '```'

        # embed = Embed(title='Voice activity', description=answer)
        # await ctx.send(embed=embed)

    def voice_activity_check(self): #make adding new users to active list
        while True:
            active_users = self.get_active_voice_users()

            for item in self.voice_activity_collection.find({'session_ended': False}):
                if item['guild'] in active_users.keys() and item['user_id'] not in active_users[item['guild_id']]:
                    self.voice_activity_collection.update_one({'_id': item['_id']}, {'$set': {'session_ended': True}})

            for item in self.voice_activity_collection.find({'session_ended': False}):
                item['activity_minutes'] += 1

            sleep(60)

    def get_active_voice_users(self):
        active_users = {}
        for guild in self.discord_client.guilds:
            for channel in guild.channels:
                if channel.type == ChannelType.voice:
                    guild_active_users = channel.voice_states.keys()
            active_users[guild.id] = guild_active_users
        return active_users
        
    def save_message(self, ctx):
        new_item = {
            'guild_id': ctx.guild.id,
            'timestamp': ctx.created_at,
            'author_id': ctx.author.id,
            'is_bot': ctx.author.bot,
            'channel_id': ctx.channel.id,
            'content': ctx.content,
            'attachments': ctx.attachments,
            'attachments_number': len(ctx.attachments)
        }
        self.messages_collection.insert_one(new_item)

    async def get_top(self, ctx):
        for item in self.messages_collection.find:

        # messages = models.MessageModel.select(models.MessageModel.author_id, models.MessageModel.message_content, 
        #     models.MessageModel.attachment, models.MessageModel.server_id).where(models.MessageModel.server_id == ctx.guild.id and models.MessageModel.is_bot == False)
        # voice_activities = activity_history = models.VoiceActivityModel.select(models.VoiceActivityModel.user_id, 
        #         models.VoiceActivityModel.activity_minutes, models.VoiceActivityModel.guild_id).where(models.VoiceActivityModel.guild_id == ctx.guild.id)
        # authors = self.get_authors(messages)
        # user_scores = {a: self.get_user_points(messages, voice_activities, ctx.guild.id, a) for a in authors}
        # answer = await self.create_userscores_answer(user_scores)

        # embed = Embed(title='Top', description=answer)
        # await ctx.send(embed=embed)

    # def get_authors(self, messages):
    #     authors_list = []
    #     for msg in list(messages.objects()):
    #         if msg.author_id not in authors_list:
    #             authors_list.append(msg.author_id)
    #     return authors_list

    # def get_users_by_voice(self, voice_activities):
    #     authors_list = []
    #     for msg in list(voice_activities.objects()):
    #         if msg.author_id not in authors_list:
    #             authors_list.append(msg.user_id)
    #     return authors_list

    # def get_user_points(self, messages, voice_activities, guild_id, author_id):
    #     user_points = 0.0
    #     for msg in list(messages.objects()):
    #         if(msg.author_id == author_id and msg.server_id == str(guild_id)):
    #             user_points += len(msg.message_content) * 0.1
    #             user_points += msg.attachment * 5
    #     for voice_activity in voice_activities:
    #         if voice_activity.guild_id == str(guild_id) and voice_activity.user_id == author_id:
    #             user_points += voice_activity.activity_minutes * 5
    #     return int(user_points)

    # async def create_userscores_answer(self, user_scores):
    #     fetched_scores = []

    #     for id in user_scores:
    #         nickname = await self.fetch_user(id)
    #         fetched_scores.append({'name': nickname, 'score': user_scores[id]})
    #     fetched_scores.sort(key = lambda x: x['score'])
    #     fetched_scores.reverse()

    #     answer = '```'
    #     for score in fetched_scores:
    #         answer += '#' + str(fetched_scores.index(score) + 1) + ' ' + score['name'] + ' - ' + str(score['score']) + '\n'
    #     answer += '```'
    #     return answer

    # async def fetch_user(self, id):
    #     user = await self.discord_client.fetch_user(id)
    #     return str(user.name) + "#" + str(user.discriminator)