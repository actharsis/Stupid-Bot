import models
import constants
from peewee import *

class Analysis_module:
    global sql
    global db
    global cursor


    def __init__(self):
        self.init_db()


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