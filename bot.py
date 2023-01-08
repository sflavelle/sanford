# Import essential libraries
import discord
from discord import app_commands,Colour
from discord.ext import commands
import typing
from datetime import datetime,timedelta,timezone
import asyncio
import yaml
import sys
import os
import logging
import logging.handlers
# Other helpful libraries
from pluralkit import Client as PK
import sqlite3
from dateutil.parser import *
import dateutil
# Import custom libraries
from helpers.quoting import *
from mastoposter import post_new_quote

# setup logging
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)
logging.getLogger('discord').setLevel(logging.DEBUG)

handler = logging.handlers.RotatingFileHandler(
    filename='logs/sanford.log',
    encoding='utf-8',
    maxBytes=8 * 1024 * 1024,  # 32 MiB
    backupCount=10,  # Rotate through 5 files
)
dt_fmt = '%Y-%m-%d %H:%M:%S'
formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
handler.setFormatter(formatter)
logger.addHandler(handler)

# init vars?
cfg = None

# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

# set variables
db = "db/quotes.sqlite"

# configure subscribed intents
intents = discord.Intents.default()
intents.message_content = True

# Define common targets
TGC = discord.Object(id=124680630075260928)

# setup command framework
sanford = commands.Bot(command_prefix="&",intents=intents)

# init Pluralkit API
pluralkit = PK(cfg['sanford']['pluralkit_token'])

# various helpers
def strfdelta(tdelta, fmt):
    d = {"days": tdelta.days}
    d["hours"], rem = divmod(tdelta.seconds, 3600)
    d["minutes"], d["seconds"] = divmod(rem, 60)
    return fmt.format(**d)

@sanford.command()
@commands.is_owner()
async def cmdsync(ctx):
    logger.info("Syncing commands to Discord.")
    await sanford.tree.sync()
    await sanford.tree.sync(guild=TGC)
    logger.info("Command syncing complete!")
    await ctx.send("Done.")

@sanford.command()
@commands.is_owner()
async def reboot(ctx):
    await ctx.send("Reloading the bot...")
    logger.warning("Rebooting the bot!")
    os.execv(sys.executable,['python3.11'] + sys.argv)
    
@sanford.command()
@commands.is_owner()
async def stampfinder(ctx, *, channel: typing.Union[discord.TextChannel, discord.Thread]):
   
    # Hello, me. You had this thought to automate the process of assigning timestamps to quotes
    # at midnight on January 2, 2023. Instead of sleeping. You butt.
    
    # Here's how you figured it might work:
    
    # - SQL Query for all messages from the guild that have no msgID or timestamp.
    # - use https://discordpy.readthedocs.io/en/latest/api.html#discord.TextChannel.history
    #     to fetch a complete history of the guild's main channel, and iterate through it to
    #     find messages with the same author and:
    #         - the EXACT message content
    #         - The same content, but in a 'Bucket, addquote' cmd attributed to the author
    # - If we find the message (the older the better), save that msgID and timestamp to the DB
    # - Update the updatedAt field as well
    # - When the operation is done, return how many records were updated (updated/total)
    
    # Because the operation is likely to take a bit, send a message when the operation starts,
    # and make Sanford 'type' while it's working, then follow-up when it's done
    
    # Now go to sleep
    
    # Alright, let's start by initialising a connection to the database
    
    logger.info(f"Stampfinder: Attempting to resolve missing timestamps and message IDs for quotes in #{channel.name}")
    delta = datetime.now()
        
    con = sqlite3.connect(db) # autocommit=False for now, as I don't want to break the database in production with these changes
    cur = con.cursor() 
    
    cur.execute(f"SELECT id,content,authorID FROM quotes WHERE guild='{str(ctx.guild.id)}' AND authorID != '' AND timestamp IS NULL ORDER BY id ASC")
    
    # Sadly, SELECT statements don't have a rowcount or len in the cur, so we /have/ to fetchall
    untimestamped = cur.fetchall()
    
    logger.info(f"Returned {str(len(untimestamped))} quotes in need of a timestamp or msgID")
    if len(untimestamped) == 0: 
        await ctx.send(f"Actually, these quotes need no action!")
        logger.info("Stampfinder: No action needed")
    else:
        # Calculate how long it might take to do
        async with ctx.typing():
            msgtimes = []
            async for message in channel.history(limit=300):
                msgtimes.append(message.created_at)
            
            msgdeltas = [msgtimes[i-1]-msgtimes[i] for i in range(1, len(msgtimes))]
            
            avgmsgdelta = sum(msgdeltas, timedelta(0)) / len(msgdeltas)
            logger.info(f"Stampfinder: average time between msgs: {avgmsgdelta.total_seconds()} seconds")
            
            channeldelta = datetime.now(timezone.utc) - channel.created_at
            logger.info(f"Stampfinder: Channel {channel.name} has existed for {channeldelta.days} days")
            
            # channel.history can fetch 500 messages at a time every few seconds so... maybe??

            estimatedelta = timedelta(channeldelta / avgmsgdelta) / (5*500*(1*60*60*24)) * (len(untimestamped)/5)
            logger.info("Stampfinder: Estimate:")
            logger.info(estimatedelta)
        
        
        confirm = await ctx.send(f"I can try to find as many quotes as I can, but this will probably take a very long time (rough estimate: **{strfdelta(estimatedelta, '{hours} hours, {minutes} minutes, {seconds} seconds')}** for a channel created **{channel.created_at.strftime('%B %Y')}**)...\nGo ahead and react with anything to confirm.")
        
        def react_wait(reaction,userreact):
            return userreact == sanford.application.owner and reaction.message.id == confirm.id
        react = None
        try: 
            react = await sanford.wait_for("reaction_add",timeout=60,check=react_wait)
        except TimeoutError as error:
            logger.info("Stampfinder: Cancelled.")
            await confirm.edit(content="I didn't see a reaction from you, so we'll leave it for now.",delete_after=10)
            await ctx.message.delete(delay=10)
            await confirm.clear_reactions()
        
        if react is not None:
        
            await ctx.send(f"Okay, I'm going to try to find message info for {str(len(untimestamped))} quotes using <#{channel.id}>\n\nThis is likely to take a very, *very* long time, as I can only search 500 messages at a time.")
            
            logger.info("Stampfinder: Here we go")
            
            msgcounter = 0 # Count total messages
            hitcounter = 0 # Count matching messages
                        
            progressmsg = await ctx.send(f"**Progress:** **{msgcounter}** messages searched, **{hitcounter}/{len(untimestamped)}** quote timestamps found.")
            
            async with ctx.typing():
                          
                async for message in channel.history(limit=None,oldest_first=True): # limit=None when this is complete
                    if msgcounter == 0:
                        logger.info(f"processing message {msgcounter} (currently exploring {message.created_at.strftime('%B %d, %Y')})")
                    msgcounter += 1
                    logger.debug(f"processing message {msgcounter} (currently exploring {message.created_at.strftime('%B %d, %Y')})")
                    if msgcounter % 1000 == 0:
                        logger.info(f"processing message {msgcounter} (currently exploring {message.created_at.strftime('%B %d, %Y')})")
                        await progressmsg.edit(content = f"**Progress:** **{msgcounter}** messages searched, **{hitcounter}/{len(untimestamped)}** quote timestamps found.")
                    for row in untimestamped:
                        # First, check that between when we started and now,
                        # we did not get a timestamp/message ID added

                        # This of course
                        cur.execute(f"SELECT 1 from quotes WHERE id='{row[0]}' AND (timestamp IS NULL OR msgID IS NULL)")
                        check_dupe = cur.fetchall()
                        
                        if not(bool(check_dupe)):
                            logger.debug("We already found a quote associated with this message")
                            continue
                        
                        if (row[1] == message.content and int(row[2]) == message.author.id) or (row[1] in message.content and int(row[2]) == message.author.id) or (row[1] in message.clean_content and int(row[2]) in message.raw_mentions):
                            if message.author.id == sanford.user.id:
                                continue # Don't add confirmation messages from Sanford as the message ID itself
                            elif message.content.startswith('b!addquote'):
                                continue # Pre-Bucket/Sanford string circa 2016
                                # This basically means we tried to add it from IRC or another prior network
                                # Ergo, this is not a timestamp we want
                                
                            logger.info(f"Stampfinder: Found quote ID {row[0]} in msg ID {message.id} timestamp {message.created_at.strftime('%Y-%m-%d %H:%M:%S.%f %z')}")
                            logger.debug(f'quote content: {row[1]}\nquote author: {row[2]}')
                            logger.debug(f'message content: {message.content}\nmessage author: {message.author.id}')
                            
                            # OK, this is the part where we actually update the database
                            try: 
                                cur.execute("UPDATE quotes SET msgID=?, timestamp=?, updatedAt=? WHERE ID=?", (
                                    message.id, 
                                    int(datetime.timestamp(message.created_at)),
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
                                    int(row[0])
                                    ))
                            except sqlite3.Error as error:
                                await ctx.send(f'Error: SQL Update Failed due to:\n```{str(error)}```')
                                logger.error("QUOTE SQL ERROR:\n" + str(error))
                                break

                            hitcounter += 1
                            
                            continue
                    
                    # progressmsg.delete()
            con.commit()
            delta = datetime.now() - delta
            logger.info(f"Done! Found sources for {str(hitcounter)} out of {str(len(untimestamped))} quotes in {str(msgcounter)} messages in #{channel.name}")
            await ctx.send(f"Done! Found sources for **{str(hitcounter)}** out of {str(len(untimestamped))} quotes in **{str(msgcounter)} messages** in <#{channel.id}>.\nTime taken: **{strfdelta(delta, '{hours} hours, {minutes} minutes, {seconds} seconds')}**.")
    con.close()
        
@stampfinder.error
async def stampfinder_err(ctx, error):
    if isinstance(error, commands.BadArgument):
        await ctx.send("Can't find that channel mate.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("You need to provide a channel for me to search through.")
    else:
        await ctx.send(error)
        logger.error(error)

@sanford.tree.command()
@app_commands.guilds(TGC)
@app_commands.rename(exclude_in_mastoposter='dont_send_quotes')
@app_commands.describe(exclude_in_mastoposter="Exclude your quotes from being posted to @tgcooc?")
async def mastodon(interaction: discord.Interaction, exclude_in_mastoposter: bool):
    """Configure settings relating to you in the @tgcooc Mastodon account."""
    global cfg
    try:
        if exclude_in_mastoposter is not None:
            if exclude_in_mastoposter == True:
                cfg['mastodon']['exclude_users'].append(interaction.user.id)
            else: cfg['mastodon']['exclude_users'].remove(interaction.user.id)
            with open('config.yaml', 'w') as file:
                yaml.dump(cfg, file)
            with open('config.yaml', 'r') as file:
                cfg = yaml.safe_load(file)
            logger.info(f"/mastodon: {interaction.user.name} added themselves to the excluded_users list")
            await interaction.response.send_message("Your settings were updated.",ephemeral=True)
    except io.UnsupportedOperation as error:
        logger.error("Issue reading the config file!", error)
        await interaction.response.send_message("There was an issue reading the file.",ephemeral=True)

quote_group = app_commands.Group(name='quote',description='Save or recall memorable messages')

@quote_group.command(name="get")
async def quote_get(interaction: discord.Interaction, user: discord.Member=None):
    """Get a random quote!"""
    try:
        if bool(user):
            qid,content,aID,aName,timestamp,karma = user_random_quote("db/quotes.sqlite",interaction.guild_id, user.id)
        else:
            qid,content,aID,aName,timestamp,karma = fetch_random_quote("db/quotes.sqlite",interaction.guild_id)
    except LookupError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return

    qvote_timeout = cfg['sanford']['quoting']['vote_timeout']
    
    # Is the user still in the server?
    authorObject = None
    try: 
        authorObject = await interaction.guild.fetch_member(aID)
    except:
        pass
        
    
    quoteview = discord.Embed(
        description=format_quote(content, timestamp, authorID=aID if bool(authorObject) else None, authorName=aName, format='markdown')
    )
    if bool(authorObject):
        authorAvatar = authorObject.display_avatar
        quoteview.set_thumbnail(url=authorAvatar.url)
    else:
        quoteview.set_thumbnail(url="https://cdn.thegeneral.chat/sanford/special-avatars/sanford-quote-noicon.png")
    quoteview.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma}. Voting is open for {qvote_timeout} minutes.")
    # Send the resulting quote
    await interaction.response.send_message(allowed_mentions=discord.AllowedMentions.none(),embed=quoteview)
    
    # Let's allow the quote to be voted on
    thumbsUp, thumbsDown = "👍", "👎"
    
    qmsg = await interaction.original_response()
    
    await qmsg.add_reaction(thumbsUp)
    await qmsg.add_reaction(thumbsDown)
    
    
    await asyncio.sleep(60*qvote_timeout) # Wait 3 minutes before collecting reactions
    
    qmsg = await interaction.channel.fetch_message(qmsg.id)
    
    upCount = 0
    downCount = 0
    
    # Count the reactions (Sanfords doesn't count)
    for e in qmsg.reactions:
        match e.emoji:
            case "👍":
                upCount = e.count - 1
            case "👎":
                downCount = e.count - 1
                
    karmadiff = 0 + upCount - downCount
    newkarma = karma + karmadiff
    
    quoteview.set_footer(text=f"Score: {'+' if newkarma > 0 else ''}{newkarma} ({'went up by +{karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff > 0 else 'went down by {karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff < 0 else 'did not change'} this time).")
    
    update_karma(db,qid,newkarma)
    await qmsg.edit(embed=quoteview)
    await qmsg.clear_reactions()

@quote_group.command(name="add")
@app_commands.describe(author='User who said the quote',content='The quote itself',time='When the quote happened')
async def quote_addbyhand(interaction: discord.Interaction, author: discord.Member, content: str, time: str=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z")):
    """Create a quote manually, eg. for things said in VOIP"""
    try:
        con = sqlite3.connect(db)
        cur = con.cursor()
        
        # Parse entered timestamp
        timestamp = parse(time, default=datetime.now())
        
        sql_values = list((
            content,
            author.id,
            author.name,
            interaction.user.id,
            interaction.guild_id,
            None,
            int(datetime.timestamp(timestamp)),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z")
        ))
        
        cur.execute("INSERT INTO quotes (content, authorID, authorName, addedBy, guild, msgID, timestamp, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", sql_values)
        con.commit()

        logger.info("Quote saved successfully")
        logger.debug(format_quote(content, authorName=author.name, timestamp=int(datetime.timestamp(timestamp))))
        
        quote = format_quote(content, authorName=author.name, timestamp=int(datetime.timestamp(timestamp)), format='discord_embed')
        quote.add_field(name='Status',value=f'Quote saved successfully.')
        authorAvatar = author.display_avatar
        quote.set_thumbnail(url=authorAvatar.url)

        await interaction.response.send_message(
            embed=quote,
            allowed_mentions=discord.AllowedMentions.none()
            )
        
        if interaction.guild_id == 124680630075260928 and author.id not in cfg['mastodon']['exclude_users']:
            post_new_quote(content, author.id, int(datetime.timestamp(timestamp)))
        
        con.close()
    except sqlite3.Error as error:
        await interaction.response.send_message(f'Error: SQL Failed due to:\n```{str(error.with_traceback)}```',ephemeral=True)
        logger.error("QUOTE SQL ERROR:\n" + str(error.with_traceback))
    except dateutil.parser._parser.ParserError as error:
        await interaction.response.send_message(f'Error: {error}',ephemeral=True)
        
sanford.tree.add_command(quote_group)

@sanford.tree.context_menu(name='Save as quote!')
async def quote_save(interaction: discord.Interaction, message: discord.Message):

    try:
        con = sqlite3.connect(db)
        cur = con.cursor()

        # Check for duplicates first
        check_dupe = cur.execute("SELECT 1 from quotes WHERE msgID='" + str(message.id) + "'")
        if check_dupe.fetchone() is not None:
            raise LookupError('This quote is already in the database.')

        sql_values = list((
            message.content, 
            message.author.id,
            message.author.name,
            interaction.user.id,
            interaction.guild_id,
            message.id,
            int(datetime.timestamp(message.created_at)),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z")
            ))

        # # PluralKit check
        if message.webhook_id:
            try:
                pkmsg = await pluralkit.get_message(message.id)
                print(pkmsg)
                if pkmsg is not None:
                    sql_values[1] = int(pkmsg.sender)
            except AttributeError as error:
                logger.error("Fetching PluralKit author from message failed - message too old?")
                try:
                    logger.info("Trying to infer author from name substring...")
                    pkauthor = message.author.name
                    for k,v in cfg['sanford']['pluralkit_mapping'].items():
                        if v in pkauthor:
                            # Found our author!
                            logger.info(f"Found 'em: Author is ID {k}")
                            sql_values[1] = int(k)
                            break
                    else:
                        raise KeyError("Could not find a user ID to map this message to.")
                except KeyError as error:
                    logger.error(f"Could not fetch webhook msg author for '{message.author.name}'")
                    await interaction.response.send_message(error,ephemeral=True)
                except TypeError as error:
                    await interaction.response.send_message(error.with_traceback,ephemeral=True)
                    logger.error("TypeError somewhere in the PK check code!", error.with_traceback)
        
        cur.execute("INSERT INTO quotes (content, authorID, authorName, addedBy, guild, msgID, timestamp, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", sql_values)
        con.commit()

        quote = format_quote(message.content, authorID=message.author.id, timestamp=int(message.created_at.timestamp()), format='discord_embed')
        quote.add_field(name='Status',value=f'[Quote]({message.jump_url}) saved successfully.')
        
        authorAvatar = message.author.display_avatar
        quote.set_thumbnail(url=authorAvatar.url)

        logger.info("Quote saved successfully")
        logger.debug(format_quote(message.content, authorName=message.author.name, timestamp=int(message.created_at.timestamp())),)

        await interaction.response.send_message(
            embed=quote,
            allowed_mentions=discord.AllowedMentions.none()
            )
        
        if interaction.guild_id == 124680630075260928 and message.author.id not in cfg['mastodon']['exclude_users']:
            post_new_quote(message.content, (sql_values[1] if message.webhook_id else message.author.id), int(message.created_at.timestamp()))
        
        con.close()

    except sqlite3.Error as error:
        await interaction.response.send_message(f'Error: SQL Failed due to:\n```{str(error.with_traceback)}```',ephemeral=True)
        logger.error("QUOTE SQL ERROR:\n" + str(error.with_traceback))
    except LookupError as error:
        await interaction.response.send_message('Good News! This quote was already saved.',ephemeral=True)
        logger.info("Quote was already saved previously")

@sanford.event
async def on_ready():
    logger.info(f"Logged in. I am {sanford.user} (ID: {sanford.user.id})")

sanford.run(cfg['sanford']['discord_token'], log_handler=handler)
