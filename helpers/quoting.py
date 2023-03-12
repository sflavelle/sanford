from datetime import datetime
import psycopg2
import discord
import yaml
import re
import asyncio

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

### SQL FUNCTIONS

def fetch_random_quote(gid,exclude_list: list=list(())):
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
)
    cur = con.cursor()
    exclude = ""
    if bool(exclude_list):
        exclude = f"AND authorid NOT IN ({str(exclude_list).strip('[]')})"

    # Fetch a random quote from the SQL database
    try:
        cur.execute(f"SELECT id,content,authorid,authorname,timestamp,karma FROM bot.quotes WHERE guild='{str(gid)}' AND authorid is not null {exclude if bool(exclude_list) else ''} ORDER BY random() LIMIT 1")
        id,content,aID,aName,timestamp,karma = cur.fetchone()
    except TypeError as error:
        if "NoneType object" in str(error):
            raise LookupError("Sorry, there aren't any quotes saved in this server yet.\n\nTo save a quote, right-click a message and navigate to `Apps > Save as quote!`. If you want to save a message manually (eg. something said in voice, IRL or in a game), the `/quote add` command will help you save those quotes.")
    cur.close()
    con.close()
    return (id, content, aID, aName, timestamp, karma)

def user_random_quote(gid,uid,exclude_list: list=list(())):
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
)
    cur = con.cursor()
    exclude = ""
    if bool(exclude_list):
        exclude = f"AND authorid NOT IN ({str(exclude_list).strip('[]')})"

    # Fetch a random quote from the SQL database
    try:
        cur.execute(f"SELECT id,content,authorid,authorname,timestamp,karma FROM bot.quotes WHERE guild='{str(gid)}' AND authorid = {int(uid)} {exclude if bool(exclude_list) else ''} ORDER BY random() LIMIT 1")
        id,content,aID,aName,timestamp,karma = cur.fetchone()
    except TypeError as error:
        if bool(uid) and "NoneType object" in str(error):
            raise LookupError("Sorry, that user doesn't have any quotes saved in this server yet!")
    cur.close()
    con.close()
    return (id, content, aID, aName, timestamp, karma)

def insert_quote(quote_data: tuple):
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
    )
    cur = con.cursor()
    
    # Validate quote tuple first
    if len(quote_data) != 7:
        raise Exception(f"Quote object has {len(quote_data)} items (should be 7)")
    
    
    cur.execute("INSERT INTO bot.quotes (content, authorid, authorname, addedby, guild, msgid, timestamp) VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id, karma;", quote_data)
    returning = cur.fetchone()
    con.commit()
    cur.close()
    con.close()
    return returning

def update_karma(qid,karma):
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
    )
    cur = con.cursor()
    cur.execute("UPDATE bot.quotes SET karma= %s WHERE id= %s", (karma, qid))
    con.commit()
    cur.close()
    con.close()
    
async def karma_helper(interaction: discord.Interaction, qid, karma):
    # config vars
    timeout = cfg['sanford']['quoting']['vote_timeout']
    # Let's allow the quote to be voted on
    thumbsUp, thumbsDown = "👍", "👎"
    
    imsg = await interaction.original_response()
    msg = await imsg.fetch()
    
    await msg.add_reaction(thumbsUp)
    await msg.add_reaction(thumbsDown)
    
    
    await asyncio.sleep(60*timeout) # Wait 3 minutes before collecting reactions
    
    msg = await msg.fetch()
    
    upCount = 0
    downCount = 0
    
    # Count the reactions (Sanfords doesn't count)
    for e in msg.reactions:
        match e.emoji:
            case "👍":
                upCount = e.count - 1
            case "👎":
                downCount = e.count - 1
                
    karmadiff = 0 + upCount - downCount
    newkarma = karma + karmadiff
    
    return (qid, newkarma)
    
### MASTOPOSTER-CENTRIC FUNCTIONS
    
def rename_user(id, fallback: str):
    for k,v in cfg['mappings']['users'].items():
        if k == id:
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
        str = str.replace(f"<@{match.group(1)}>", rename_user(match.group(1), '(user id here, no match)'))
        str = str.replace(f"<@!{match.group(1)}>", rename_user(match.group(1), '(user id here, no match)'))
        
    return str
            
    