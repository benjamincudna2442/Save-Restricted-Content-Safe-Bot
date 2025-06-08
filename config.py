# safe_repo
# Note if you are trying to deploy on vps then directly fill values in ("")

from os import getenv

API_ID = int(getenv("API_ID", "26512884"))
API_HASH = getenv("API_HASH", "c3f491cd59af263cfc249d3f93342ef8")
BOT_TOKEN = getenv("BOT_TOKEN", "7576323615:AAEwbi4d7k4Q8UTQgBGT2vi0O60bxapX3tI")
OWNER_ID = list(map(int, getenv("OWNER_ID", "7303810912 5991909954").split()))
MONGO_DB = getenv("MONGO_DB", "mongodb+srv://ytpremium4434360:zxx1VPDzGW96Nxm3@itssmarttoolbot.dhsl4.mongodb.net/?retryWrites=true&w=majority&appName=ItsSmartToolBot")
LOG_GROUP = getenv("LOG_GROUP", "-1002888716176")
CHANNEL_ID = int(getenv("CHANNEL_ID", "-1002740254173"))
