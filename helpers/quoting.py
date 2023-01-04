from datetime import datetime
import sqlite3
import discord

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
    quote = cur.execute(f"SELECT id,content,authorID,authorName,timestamp,karma FROM quotes WHERE guild='{str(gid)}' AND authorID != '' {exclude if bool(exclude_list) else ''} ORDER BY random() LIMIT 1")
    id,content,aID,aName,timestamp,karma = quote.fetchone()
    con.close()
    return (id, content, aID, aName, timestamp, karma)

def user_random_quote(db: str,gid,uid,exclude_list: list=list(())):
    con = sqlite3.connect(db)
    cur = con.cursor()
    exclude = ""
    if bool(exclude_list):
        exclude = f"AND authorID NOT IN ({str(exclude_list).strip('[]')})"

    # Fetch a random quote from the SQL database
    quote = cur.execute(f"SELECT id,content,authorID,authorName,timestamp,karma FROM quotes WHERE guild='{str(gid)}' AND authorID = '{str(uid)}' {exclude if bool(exclude_list) else ''} ORDER BY random() LIMIT 1")
    id,content,aID,aName,timestamp,karma = quote.fetchone()
    con.close()
    return (id, content, aID, aName, timestamp, karma)

def update_karma(db: str,qid,karma):
    con = sqlite3.connect(db)
    cur = con.cursor()
    cur.execute("UPDATE quotes SET karma=? WHERE ID=?", (karma, qid))
    con.commit()
    con.close()