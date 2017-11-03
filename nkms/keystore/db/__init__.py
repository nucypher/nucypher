from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.engine import Engine
from sqlalchemy import event


Base = declarative_base()


@event.listens_for(Engine, "connect")
def set_secure_delete_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA secure_delete=on")
    cursor.close()
