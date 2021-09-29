import models
import constants
from time import sleep
from discord import ChannelType
from threading import *
from peewee import *

class Analysis_module:
    global db
    global cursor
    global discord_client
    global voice_activity_thread

    def __init__(self, client):
        self.init_db()
        self.discord_client = client
        self.voice_activity_thread = Thread(target = self.voice_activity_check)
        self.voice_activity_thread.start()

    def __del__(self):
        self.db.commit()
        self.db.close()

    def init_db(self):
        self.db = SqliteDatabase(constants.DATABASE_DIR)
        self.cursor = self.db.cursor()

        self.db.create_tables([models.MessageModel, models.VoiceActivityModel])

    def voice_activity_check(self):
        while True:
            activity_history = models.VoiceActivityModel.select(models.VoiceActivityModel.id, models.VoiceActivityModel.user_id, 
                models.VoiceActivityModel.activity_minutes, models.VoiceActivityModel.guild_id)
            for guild in self.discord_client.guilds:
                members = []
                for channel in guild.channels:
                    if(channel.type == ChannelType.voice):
                        for member in channel.voice_states.keys():
                            members.append(member)
                for member in members:
                    is_new_user = True
                    for i in range(len(activity_history.objects())):
                        if activity_history.objects()[i].guild_id == str(guild.id) and \
                            activity_history.objects()[i].user_id == str(member):
                                new_record = activity_history.objects()[i]
                                new_record.activity_minutes += 1
                                new_record.save()
                                is_new_user = False
                    if is_new_user:
                        models.VoiceActivityModel.create(user_id = member, activity_minutes = 1, guild_id = guild.id)
            sleep(60)
        
    def save_message(self, message):
        models.MessageModel.create(server_id = message.guild.id,
        message_datetime = message.created_at, author_id = message.author.id,
        is_bot = message.author.bot, channel_id = message.channel.id,
        message_content = message.content, attachment = len(message.attachments))

    async def get_top(self, message):
        messages = models.MessageModel.select(models.MessageModel.author_id, models.MessageModel.message_content, 
            models.MessageModel.attachment, models.MessageModel.server_id).where(models.MessageModel.server_id == message.guild.id)
        voice_activities = activity_history = models.VoiceActivityModel.select(models.VoiceActivityModel.user_id, 
                models.VoiceActivityModel.activity_minutes, models.VoiceActivityModel.guild_id)
        authors = self.get_authors(messages)
        user_scores = {a: self.get_user_points(messages, voice_activities, message.guild.id, a) for a in authors}
        answer = await self.create_userscores_answer(user_scores)
        await message.channel.send(answer)

    def get_authors(self, messages):
        authors_list = []
        for msg in list(messages.objects()):
            if msg.author_id not in authors_list:
                authors_list.append(msg.author_id)
        return authors_list

    def get_user_points(self, messages, voice_activities, guild_id, author_id):
        user_points = 0.0
        for msg in list(messages.objects()):
            if(msg.author_id == author_id and msg.server_id == str(guild_id)):
                user_points += len(msg.message_content) * 0.1
                user_points += msg.attachment * 5
        for voice_activity in voice_activities:
            if voice_activity.guild_id == str(guild_id) and voice_activity.user_id == author_id:
                user_points += voice_activity.activity_minutes * 5
        return int(user_points)

    async def create_userscores_answer(self, user_scores):
        fetched_scores = []

        for id in user_scores:
            nickname = await self.fetch_user(id)
            fetched_scores.append({'name': nickname, 'score': user_scores[id]})
        fetched_scores.sort(key = lambda x: x['score'])
        fetched_scores.reverse()

        answer = '```'
        for score in fetched_scores:
            answer += '#' + str(fetched_scores.index(score) + 1) + ' ' + score['name'] + ' - ' + str(score['score']) + '\n'
        answer += '```'
        return answer

    async def fetch_user(self, id):
        user = await self.discord_client.fetch_user(id)
        return str(user.name) + "#" + str(user.discriminator)