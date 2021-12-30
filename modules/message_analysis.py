from models import MessageModel as mem, VoiceActivityModel as vam
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

        self.db.create_tables([mem, vam])

    async def get_voice_activity(self, ctx):
        voice_activities = vam.select(vam.user_id, 
                vam.activity_minutes, vam.guild_id)
                
        users_activity = []
        for voice_activity in voice_activities.objects():
            if voice_activity.guild_id == str(ctx.guild.id):
                users_activity.append({'user_id': voice_activity.user_id, 'activity': voice_activity.activity_minutes / 60})

        users_activity.sort(key = lambda x: x['activity'])
        users_activity.reverse()
        answer = '```'
        for activity in users_activity:
            answer += '#' + str(users_activity.index(activity) + 1) + ' ' + await self.fetch_user(activity['user_id']) + ' - ' + str(round(activity['activity'], 2)) + 'h' '\n'
        answer += '```'
        await ctx.channel.send(answer)

    def voice_activity_check(self):
        while True:
            activity_history = vam.select(vam.id, vam.user_id, 
                vam.activity_minutes, vam.guild_id)
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
                        vam.create(user_id = member, activity_minutes = 1, guild_id = guild.id)
            sleep(60)
        
    def save_message(self, message):
        mem.create(server_id = message.guild.id,
        message_datetime = message.created_at, author_id = message.author.id,
        is_bot = message.author.bot, channel_id = message.channel.id,
        message_content = message.content, attachment = len(message.attachments),
        mention=(message.reference is not None and message.reference.resolved.author.id == self.discord_client.user.id))

    def load_conversation(self, user_id, lim=10):
        return list(mem.select(mem.server_id, mem.message_datetime, mem.author_id, mem.message_content, mem.mention).where(mem.author_id==user_id).order_by(mem.message_datetime).desc().limit(lim))

    async def get_top(self, ctx):
        messages = mem.select(mem.author_id, mem.message_content, 
            mem.attachment, mem.server_id).where(mem.server_id == ctx.guild.id)
        voice_activities = activity_history = vam.select(vam.user_id, 
                vam.activity_minutes, vam.guild_id)
        authors = self.get_authors(messages)
        user_scores = {a: self.get_user_points(messages, voice_activities, ctx.guild.id, a) for a in authors}
        answer = await self.create_userscores_answer(user_scores)
        await ctx.channel.send(answer)

    def get_authors(self, messages):
        return list(set([msg.author_id for msg in messages.objects()]))

    def get_users_by_voice(self, voice_activities):
        return list(set([va.author_id for va in voice_activities.objects()]))

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