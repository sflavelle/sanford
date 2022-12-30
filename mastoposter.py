from mastodon import Mastodon
import yaml
import sqlite3
import re
import argparse

con = sqlite3.connect("db/quotes.sqlite")
cur = con.cursor()

import schedule
import time
from datetime import datetime

from helpers.quoting import format_quote,fetch_random_quote

# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

mastodon = Mastodon(
        access_token = cfg['mastodon']['access_token'],
        api_base_url = cfg['mastodon']['api_base_url']
)

post_string = '''"{0}"
    —{1} / {2}'''

def rename_user(id: str):
    # If authorname is empty for some reason
    # map the authorID to a name
    match id:
        case "49345026618036224":
            return "itdiot"
        case "162712755445432321":
            return "Trikitiger"
        case "190729135771877376":
            return "spicy"
        case "250947682758164491":
            return "Sanford"
        case "211125155194208257":
            return "Beatbot"
        case "64612757739147264":
            return "vidvisionify"
        case "186902083021045762":
            return "sam"
        case "64598978380955648":
            return "inbtwn"
        case "444971605383315487":
            return "Harmony Friends"
        case "138786599033896960":
            return "Harmony Friends"
        case "104679344806309888":
            return "glitch"
        case "78316152614301696":
            return "bnuuy"
        case "217865688868585473":
            return "Casey"
        case "104004382516867072":
            return "hube situation"
        case "481903690979082245":
            return "HYPERLINK"
        case "191487004448391169":
            return "lackingsaint"
        case "218527740381495297":
            return "Leiden"
        case "159071956161789962":
            return "Lionel Stephenson"
        case "206536805997084677":
            return "unlobito"
        case "49288117307310080":
            return "Splatsune"
        case "264242512565108736":
            return "Quetz"
        case "187009387813011457":
            return "Faye"
        case "526133265334140930":
            return "Billdozer"
        case _:
            return "(@splatsune@thegeneral.chat didn't map this user's ID. SHAME! This quoted user's ID is " + str(id) + ")"

def post_new_quote(content, aID, timestamp):

    # Scrub Discord-specific formatting
    content = re.sub("<(:\S+:)\d+>","\g<1>",content)

    quote = format_quote(content,authorName=rename_user(aID),timestamp=timestamp) 
    mastodon.status_post(quote)

# Main script
if __name__ == "__main__":

    arguments =  argparse.ArgumentParser(
        description= 'Posts quotes to Mastodon every 2 hours!'
    )

    arguments.add_argument('--debug', action='store_true', help='Debug mode. Posts every two minutes instead')
    args = arguments.parse_args()


    def post():
        content,aID,aName,timestamp = fetch_random_quote("db/quotes.sqlite",124680630075260928)

        content = re.sub("<(:\S+:)\d+>","\g<1>",content)
        
        # Console logging
        print("'" + content + "' - " + aName + " (ID " + aID + ", timestamp " + str(timestamp) + ")")

        quote = format_quote(content,authorName=rename_user(aID),timestamp=timestamp)
            
        mastodon.status_post(quote)

    if args.debug == True:
        # Schedule to run every 3 minutes (for testing)
        print('Debug Mode: Posting every 2 minutes')
        schedule.every(2).minutes.do(post)
    else:
        # Schedule to run every 2 hours
        print('Posting every 2 hours')
        schedule.every(2).hours.at("00:00").do(post)

    while True:
        schedule.run_pending()
        time.sleep(3)
