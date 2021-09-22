import models
import constants
from peewee import *

class Analysis_module:
    global sql
    global db
    global cursor
    global discord_client


    def __init__(self, client):
        self.init_db()
        self.discord_client = client


    def __del__(self):
        self.db.commit()
        self.db.close()


    def init_db(self):
        self.db = SqliteDatabase(constants.DATABASE_DIR)
        self.cursor = self.db.cursor()

        self.db.create_tables([models.MessageModel])


    def save_message(self, message):
        models.MessageModel.create(server_id = message.guild.id,
        message_datetime = message.created_at, author_id = message.author.id,
        is_bot = message.author.bot, channel_id = message.channel.id,
        message_content = message.content, attachment = len(message.attachments))


    async def get_top(self, message):
        messages = models.MessageModel.select(models.MessageModel.author_id, 
            models.MessageModel.message_content).where(models.MessageModel.server_id == message.guild.id)
        authors = self.get_authors(messages)
        user_scores = {}
        for a in authors:
            user_scores[a] = self.get_user_points(messages, a)
        answer = await self.create_userscores_answer(user_scores)
        await message.channel.send(answer)


    def get_authors(self, messages):
        authors_list = []
        for msg in list(messages.objects()):
            if msg.author_id not in authors_list:
                authors_list.append(msg.author_id)
        return authors_list


    def get_user_points(self, messages, author_id):
        user_points = 0.0
        for msg in list(messages.objects()):
            if(msg.author_id == author_id):
                user_points += len(msg.message_content) * 0.1
        return round(user_points, 2)


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

