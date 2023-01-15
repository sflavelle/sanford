from mastodon import Mastodon
import yaml
import psycopg2
import re
import argparse
from helpers.quoting import rename_user,strip_discord_format


import schedule
import time
from datetime import datetime

from helpers.quoting import format_quote,fetch_random_quote

# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

con = psycopg2.connect(
    database = cfg['postgresql']['database'],
    host = cfg['postgresql']['host'],
    user = cfg['postgresql']['user'],
    password = cfg['postgresql']['password'],
)
cur = con.cursor()

mastodon = Mastodon(
        access_token = cfg['mastodon']['access_token'],
        api_base_url = cfg['mastodon']['api_base_url']
)

post_string = '''"{0}"
    —{1} / {2}'''

def post_new_quote(content, aID, timestamp):

    # Scrub Discord-specific formatting
    content = strip_discord_format(content)


    quote = format_quote(content,authorName=rename_user(aID,f'(@splatsune@thegeneral.chat has no map for user {aID}!)'),timestamp=timestamp) 
    mastodon.status_post(quote)

# Main script
if __name__ == "__main__":

    arguments =  argparse.ArgumentParser(
        description= 'Posts quotes to Mastodon every 2 hours!'
    )

    arguments.add_argument('--debug', action='store_true', help='Debug mode. Posts every two minutes instead')
    args = arguments.parse_args()


    def post():
        id,content,aID,aName,timestamp,karma = fetch_random_quote(124680630075260928, cfg['mastodon']['exclude_users'])

        content = strip_discord_format(content)
        
        # Console logging
        print("'" + content + "' - " + rename_user(aID, f'no map for user {str(aID)}') + " (ID " + str(aID) + ", timestamp " + str(timestamp) + ")")

        quote = format_quote(content,authorName=rename_user(aID,f'(@splatsune@thegeneral.chat has no map for user {aID}!)'),timestamp=timestamp)
            
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
