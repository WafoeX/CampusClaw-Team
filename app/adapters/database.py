from sqlalchemy import URL, create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.exc import SQLAlchemyError as DatabaseError

__all__ = ["DatabaseError", "IntegrityError", "mysql_engine"]


def mysql_engine(*, host, port, database, user, password):
    url = URL.create(
        "mysql+pymysql",
        username=user,
        password=password,
        host=host,
        port=port,
        database=database,
        query={"charset": "utf8mb4"},
    )
    return create_engine(
        url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 2, "read_timeout": 5, "write_timeout": 5},
    )
