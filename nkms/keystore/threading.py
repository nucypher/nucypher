from sqlalchemy.orm import sessionmaker, scoped_session


class ThreadedSession:

    def __init__(self, sqlalchemy_engine):
        self.engine = sqlalchemy_engine

    def __enter__(self):
        session_factory = sessionmaker(bind=self.engine)
        self.session = scoped_session(session_factory)
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.remove()