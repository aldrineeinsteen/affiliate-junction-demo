from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()

# Serve static assets from web/assets
app.mount("/assets", StaticFiles(directory="web/assets"), name="assets")

# Jinja2 templates in web/templates
templates = Jinja2Templates(directory="web/templates")


# --- API endpoint ---
@app.get("/api")
def get_data():
    return {"message": "Hello from the API", "data": [1, 2, 3, 4, 5]}


# --- UI endpoint ---
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
