# Import essential libraries
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
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
from helpers.quoting import format_quote,fetch_random_quote
from mastoposter import post_new_quote

# setup logging
logger = logging.getLogger('discord')
logger.setLevel(logging.INFO)

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
async def timestampquotes(ctx):
    logger.error("This doesn't actually do anything yet.")
    
    """Hello, me. You had this thought to automate the process of assigning timestamps to quotes
    at midnight on January 2, 2023. Instead of sleeping. You butt.
    
    Here's how you figured it might work:
    
    - SQL Query for all messages from the guild that have no msgID or timestamp.
    - use https://discordpy.readthedocs.io/en/latest/api.html#discord.TextChannel.history
        to fetch a complete history of the guild's main channel, and iterate through it to
        find messages with the same author and:
            - the EXACT message content
            - The same content, but in a 'Bucket, addquote' cmd attributed to the author
    - If we find the message (the older the better), save that msgID and timestamp to the DB
    - Update the updatedAt field as well
    - When the operation is done, return how many records were updated (updated/total)
    
    Because the operation is likely to take a bit, send a message when the operation starts,
    and make Sanford 'type' while it's working, then follow-up when it's done
    
    Now go to sleep"""

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
async def quote_get(interaction: discord.Interaction):
    """Get a random quote!"""
    content,aID,aName,timestamp = fetch_random_quote("db/quotes.sqlite",interaction.guild_id)

    quote = format_quote(content,authorID=aID,timestamp=timestamp)
    # Finally, send the resulting quote
    await interaction.response.send_message(quote,allowed_mentions=discord.AllowedMentions.none())

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

        status = discord.Embed(description=f'Quote saved successfully.')

        logger.info("Quote saved successfully")
        logger.debug(format_quote(content, authorName=author.name, timestamp=int(datetime.timestamp(timestamp))))

        await interaction.response.send_message(
            format_quote(content, authorID=author.id, timestamp=int(datetime.timestamp(timestamp))),
            embed=status,
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

        status = discord.Embed(description=f'[Quote]({message.jump_url}) saved successfully.')

        logger.info("Quote saved successfully")
        logger.debug(format_quote(message.content, authorName=message.author.name, timestamp=int(message.created_at.timestamp())),)

        await interaction.response.send_message(
            format_quote(message.content, authorID=(sql_values[1] if message.webhook_id else message.author.id), timestamp=int(message.created_at.timestamp())),
            embed=status,
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

sanford.run(cfg['sanford']['discord_token'], log_handler=handler, log_level=logging.INFO)
