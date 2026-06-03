from urllib.parse import quote
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["urlencode"] = lambda s: quote(s, safe="")
