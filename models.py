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

    class Meta:
        database = db
        db_table = 'Messages'