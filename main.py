from fastapi import FastAPI
from database import create_db,get_signals
from scanner import scan
import threading
import time


app=FastAPI(
title="AI CRYPTO RADAR"
)


create_db()



def worker():

    while True:

        scan()

        time.sleep(60)



threading.Thread(
target=worker,
daemon=True
).start()



@app.get("/")
def home():

    return {
    "status":"AI CRYPTO RADAR Running"
    }



@app.get("/signals")
def signals():

    return get_signals()
