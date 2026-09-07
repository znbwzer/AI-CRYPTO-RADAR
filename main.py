from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from database import create_db,get_signals


app = FastAPI(
    title="AI CRYPTO RADAR"
)


create_db()


@app.get("/")

def home():

    return FileResponse(
        "frontend/index.html"
    )



@app.get("/signals")

def signals():

    return get_signals()



app.mount(
    "/static",
    StaticFiles(
        directory="frontend"
    ),
    name="static"
)
