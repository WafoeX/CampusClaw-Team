from http.client import HTTPConnection, HTTPSConnection
from urllib.parse import urlsplit

import pymysql


def check_mysql(settings):
    with (
        pymysql.connect(
            host=settings.mysql_host,
            port=settings.mysql_port,
            database=settings.mysql_database,
            user=settings.mysql_user,
            password=settings.mysql_password,
            connect_timeout=1,
            read_timeout=1,
            write_timeout=1,
            autocommit=True,
        ) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute("SELECT 1")
        return cursor.fetchone() == (1,)


def check_qdrant(settings):
    address = urlsplit(settings.qdrant_url)
    connection_type = HTTPSConnection if address.scheme == "https" else HTTPConnection
    connection = connection_type(address.hostname, address.port, timeout=1)
    try:
        connection.request(
            "GET",
            f"{address.path}/collections",
            headers={
                "api-key": settings.qdrant_api_key,
            },
        )
        return connection.getresponse().status == 200
    finally:
        connection.close()
