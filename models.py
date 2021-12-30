from peewee import *

db = SqliteDatabase('db/TabaBotDB.db')

class MessageModel(Model):
    id = PrimaryKeyField(unique=True)
    server_id = CharField()
    message_datetime = DateTimeField()
    author_id = CharField()
    is_bot = BooleanField()
    channel_id = CharField()
    message_content = CharField()
    attachment = IntegerField()
    mention = BooleanField()

    class Meta:
        database = db
        db_table = 'Messages'

class VoiceActivityModel(Model):
    id = PrimaryKeyField(unique=True)
    guild_id = CharField()
    user_id = CharField()
    activity_minutes = IntegerField()

    class Meta:
        database = db
        db_table = 'VoiceActivity'