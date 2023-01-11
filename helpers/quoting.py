from datetime import datetime
import sqlite3
import discord
import yaml
import re

with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

def format_quote(content,timestamp,authorID=None,authorName=None,bot=None,format: str='plain'):
    quote_string_id = '''"{0}"
    —<@{1}> / {2}'''
    quote_string_name = '''"{0}"
    —{1} / {2}'''
    mdquote_string_id = '''"{0}"
    —<@{1}> / {2}'''
    mdquote_string_name = '''"{0}"
    *—{1} / {2}*'''

    # Adjust timestamp if milliseconds included
    # For parsing later
    if len(str(timestamp)) > 10:
        timestamp = timestamp / (10 ** (len(str(timestamp)) - 10))

    # No timestamp? Fudge one
    if bool(timestamp) == False:
        dateprint = "Octember 32, " + str(datetime.today().year)
    else:
    # Else generate a date string
        date = datetime.fromtimestamp(timestamp)
        dateprint = date.strftime("%B %d, %Y")

    # Choose string based on provided info
    match format:
        case 'plain':            
            if bool(authorID):
                return quote_string_id.format(content,authorID,dateprint)
            elif bool(authorName) and not bool(authorID):
                return quote_string_name.format(content,authorName,dateprint)
        case 'markdown':
            if bool(authorID):
                return mdquote_string_id.format(content,authorID,dateprint)
            elif bool(authorName) and not bool(authorID):
                return mdquote_string_name.format(content,authorName,dateprint)
        case 'discord_embed':
            
            if bool(authorID):
                embed = discord.Embed(
                    description=mdquote_string_id.format(content,authorID,dateprint)
                )
                return embed
            elif bool(authorName) and not bool(authorID):
                embed = discord.Embed(
                    description=mdquote_string_name.format(content,authorName,dateprint)
                )
                return embed

def fetch_random_quote(db: str,gid,exclude_list: list=list(())):
    con = sqlite3.connect(db)
    cur = con.cursor()
    exclude = ""
    if bool(exclude_list):
        exclude = f"AND authorID NOT IN ({str(exclude_list).strip('[]')})"

    # Fetch a random quote from the SQL database
    try:
        quote = cur.execute(f"SELECT id,content,authorID,authorName,timestamp,karma FROM quotes WHERE guild='{str(gid)}' AND authorID != '' {exclude if bool(exclude_list) else ''} ORDER BY random() LIMIT 1")
        id,content,aID,aName,timestamp,karma = quote.fetchone()
    except TypeError as error:
        if "NoneType object" in str(error):
            raise LookupError("Sorry, there aren't any quotes saved in this server yet.\n\nTo save a quote, right-click a message and navigate to `Apps > Save as quote!`. If you want to save a message manually (eg. something said in voice, IRL or in a game), the `/quote add` command will help you save those quotes.")
    con.close()
    return (id, content, aID, aName, timestamp, karma)

def user_random_quote(db: str,gid,uid,exclude_list: list=list(())):
    con = sqlite3.connect(db)
    cur = con.cursor()
    exclude = ""
    if bool(exclude_list):
        exclude = f"AND authorID NOT IN ({str(exclude_list).strip('[]')})"

    # Fetch a random quote from the SQL database
    try:
        quote = cur.execute(f"SELECT id,content,authorID,authorName,timestamp,karma FROM quotes WHERE guild='{str(gid)}' AND authorID = '{str(uid)}' {exclude if bool(exclude_list) else ''} ORDER BY random() LIMIT 1")
        id,content,aID,aName,timestamp,karma = quote.fetchone()
    except TypeError as error:
        if bool(uid) and "NoneType object" in str(error):
            raise LookupError("Sorry, that user doesn't have any quotes saved in this server yet!")

    con.close()
    return (id, content, aID, aName, timestamp, karma)

def update_karma(db: str,qid,karma):
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("UPDATE quotes SET karma=? WHERE ID=?", (karma, qid))
    con.commit()
    con.close()
    
def rename_user(id, fallback: str):
    for k,v in cfg['mappings']['users'].items():
        if str(k) in id:
            # Found our author!
            return v
    else:
        return fallback
    
def strip_discord_format(str):
    emoji = re.compile(r"<(:\S+:)\d+>")
    user = re.compile(r"<@!?(\d+)>")
    # replace emoji mentions with just the :emoji: string
    str = re.sub(emoji,"\g<1>",str)
    
    usermatches = user.finditer(str)
    
    for match in usermatches:
        str = str.replace(f"<@{match[0]}>", rename_user(match[0], '(no id match)'))
        
    return str
            
    