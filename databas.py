import sqlite3
from datetime import datetime


DB="radar.db"


def create_db():

    conn=sqlite3.connect(DB)

    c=conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS signals(
        id INTEGER PRIMARY KEY,
        coin TEXT,
        score INTEGER,
        price REAL,
        reason TEXT,
        time TEXT
    )
    """)

    conn.commit()
    conn.close()



def save_signal(
    coin,
    score,
    price,
    reason
):

    conn=sqlite3.connect(DB)

    c=conn.cursor()


    c.execute(
    """
    INSERT INTO signals
    VALUES(NULL,?,?,?,?,?)
    """,
    (
        coin,
        score,
        price,
        reason,
        datetime.now()
        )
    )


    conn.commit()
    conn.close()



def get_signals():

    conn=sqlite3.connect(DB)

    c=conn.cursor()

    data=c.execute(
    """
    SELECT *
    FROM signals
    ORDER BY id DESC
    LIMIT 50
    """
    ).fetchall()


    conn.close()

    return data
