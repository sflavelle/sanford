from mastodon import Mastodon
import yaml
import sqlite3
import re

con = sqlite3.connect("../data/quotes.sqlite")
cur = con.cursor()

import schedule
import time
from datetime import datetime

# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

mastodon = Mastodon(
        access_token = cfg['mastodon']['access_token'],
        api_base_url = cfg['mastodon']['api_base_url']
)

post_string = '''"{0}"
    —{1} / {2}'''

def post():
    quote = cur.execute("SELECT content,authorID,authorName,timestamp FROM quotes WHERE guild='124680630075260928' AND authorID != '' OR authorName = 'The General Chat' ORDER BY random() LIMIT 1")
    content,aID,aName,timestamp = quote.fetchone()

    content = re.sub("<(:\S+:)\d+>","\g<1>",content)
    
    # Console logging
    print("'" + content + "' - " + aName + " (ID " + aID + ", timestamp " + str(timestamp) + ")")

    # Truncate timestamp length if timestamp
    # includes milliseconds (like Discord does)

    if len(str(timestamp)) > 10:
        timestamp = timestamp / (10 ** (len(str(timestamp)) - 10))

    # If authorname is empty for some reason
    # map the authorID to a name
    match aID:
        case "49345026618036224":
            aName = "itdiot"
        case "162712755445432321":
            aName = "Trikitiger"
        case "190729135771877376":
            aName = "spicy"
        case "250947682758164491":
            aName = "Sanford"
        case "64612757739147264":
            aName = "vidvisionify"
        case "186902083021045762":
            aName = "sam"
        case "64598978380955648":
            aName = "inbtwn"
        case "444971605383315487":
            aName = "Harmony Friends"
        case "138786599033896960":
            aName = "Harmony Friends"
        case "104679344806309888":
            aName = "glitch"
        case "78316152614301696":
            aName = "bnuuy"
        case "217865688868585473":
            aName = "Casey"
        case "104004382516867072":
            aName = "hube situation"
        case "481903690979082245":
            aName = "HYPERLINK"
        case "191487004448391169":
            aName = "lackingsaint"
        case "218527740381495297":
            aName = "Leiden"
        case "159071956161789962":
            aName = "Lionel Stephenson"
        case "206536805997084677":
            aName = "unlobito"
        case "49288117307310080":
            aName = "Splatsune"
        case "264242512565108736":
            aName = "Quetz"
        case "187009387813011457":
            aName = "Faye"
        case _:
            aName = "(@splatsune@thegeneral.chat didn't map this user's ID. SHAME! This quoted user's ID is " + aID + ")"

    if bool(timestamp) == False:
        dateprint = "Octember 32, " + str(datetime.today().year)
    else:
        date = datetime.fromtimestamp(timestamp)
        dateprint = date.strftime("%B %d, %Y")
        
    mastodon.status_post(post_string.format(content,aName,dateprint))

# Schedule to run every 2 hours
schedule.every(2).hours.at("00:00").do(post)
# Schedule to run every 3 minutes (for testing)
# schedule.every(3).minutes.do(post)

while True:
    schedule.run_pending()
    time.sleep(3)
