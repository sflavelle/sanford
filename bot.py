# Import essential libraries
import discord
from discord import app_commands,Colour
from discord.ext import commands
import typing
from datetime import datetime,timedelta,timezone
import asyncio
import yaml
import sys
import io
import os
import logging
from systemd.journal import JournalHandler
import traceback
# Other helpful libraries
from pluralkit import Client as PK
import psycopg2
from dateutil.parser import *
import dateutil
# Import custom libraries
from helpers.quoting import *
# from mastoposter import post_new_quote # Semi-bork

# setup logging
logger = logging.getLogger('discord')
handler = JournalHandler()
logger.setLevel(logging.INFO)
logger.addHandler(handler)

# init vars?
cfg = None


# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

qvote_timeout = cfg['sanford']['quoting']['vote_timeout']

# init database connection
con = psycopg2.connect(
    database = cfg['postgresql']['database'],
    host = cfg['postgresql']['host'],
    port = cfg['postgresql']['port'],
    user = cfg['postgresql']['user'],
    password = cfg['postgresql']['password'],
    async_ = True
)

# configure subscribed intents
intents = discord.Intents.default()
intents.message_content = True

# Define common targets
TGC = discord.Object(id=124680630075260928)

# setup command framework
sanford = commands.Bot(
	command_prefix="&",
	intents=intents,
	allowed_contexts=app_commands.AppCommandContext(guild=True,dm_channel=True,private_channel=True),
	allowed_installs=app_commands.AppInstallationType(guild=True, user=True)
	)

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
    os.execv(sys.executable,['python3.12'] + sys.argv)
    
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
    
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        port = cfg['postgresql']['port'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
    )
    
    logger.info(f"Stampfinder: Attempting to resolve missing timestamps and message IDs for quotes in #{channel.name}")
    delta = datetime.now()
        
    cur = con.cursor() 
    
    cur.execute(f"SELECT id,content,authorid FROM bot.quotes WHERE guild='{str(ctx.guild.id)}' AND authorID is not NULL AND (timestamp IS NULL OR addedby is NULL) ORDER BY id ASC")
    
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
                        await progressmsg.edit(content = f"**Progress:** **{msgcounter}** messages searched (currently exploring {message.created_at.strftime('%B %d, %Y')}), **{hitcounter}/{len(untimestamped)}** quote timestamps found.")
                    for row in untimestamped:
                        # First, check that between when we started and now,
                        # we did not get a timestamp/message ID added

                        # This of course
                        cur.execute(f"SELECT 1 from bot.quotes WHERE id='{row[0]}' AND (timestamp IS NULL OR msgID IS NULL OR addedby IS NULL)")
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
                            
                            addedby = ""
                            if message.content.startswith('Bucket, addquote') or message.content.startswith('//addquote'):
                                addedby = message.author.id
                            
                            # OK, this is the part where we actually update the database
                            try: 
                                cur.execute("UPDATE bot.quotes SET msgID= %s, timestamp= %s, updatedAt= %s, addedby = %s WHERE ID= %s", (
                                    message.id, 
                                    int(datetime.timestamp(message.created_at)),
                                    datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
                                    addedby if bool(addedby) else None,
                                    int(row[0]),
                                    ))
                            except psycopg2.DatabaseError as error:
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
    cur.close()
        
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
@app_commands.describe(	exclude_in_mastoposter="Exclude your quotes from being posted to @tgcooc?",
			masto_alias="Set your name for when you are mentioned in a quote by @tgcooc.")
async def mastodon(interaction: discord.Interaction, exclude_in_mastoposter: bool = None, masto_alias: str = None):
    """Configure settings relating to you in the @tgcooc Mastodon account."""
    global cfg
    if not(exclude_in_mastoposter) and not(masto_alias):
        await interaction.response.send_message(f"Here's what I have for you right now in relation to the quote bot at https://social.thegeneral.chat/@tgcooc :\n\nYou have chosen to **{'prevent' if interaction.user.id in cfg['mastodon']['exclude_users'] else 'allow' }** posting of your quotes on Mastodon.\nYou are currently referred to as **{cfg['mappings']['users'][interaction.user.id] if bool(cfg['mappings']['users'][interaction.user.id]) else 'nobody (masto_alias not set!)'}** if you are the author of, or mentioned in, a quote.",ephemeral=True)
    try:
        if exclude_in_mastoposter is not None:
            if exclude_in_mastoposter == True:
                cfg['mastodon']['exclude_users'].append(interaction.user.id)
                logger.info(f"/mastodon: {interaction.user.name} added themselves to the excluded_users list")
            else:
                cfg['mastodon']['exclude_users'].remove(interaction.user.id)
                logger.info(f"/mastodon: {interaction.user.name} removed themselves from the excluded_users list")
        if masto_alias is not None:
            cfg['mappings']['users'][interaction.user.id] = masto_alias
            
        with open('config.yaml', 'w') as file:
            yaml.dump(cfg, file)
        with open('config.yaml', 'r') as file:
            cfg = yaml.safe_load(file)
            await interaction.response.send_message("Your settings were updated.",ephemeral=True)
    except io.UnsupportedOperation as error:
        logger.error("Issue reading the config file!", error)
        await interaction.response.send_message("There was an issue reading the file.",ephemeral=True)

quote_group = app_commands.Group(name='quote',description='Save or recall memorable messages')

@quote_group.command(name="get")
@app_commands.describe(	expose_me="When posting your own quotes in other servers, allow quotes from anywhere.")
async def quote_get(interaction: discord.Interaction, user: discord.User=None, expose_me: bool = False):
    """Get a random quote!"""
    
    try:
        if bool(user) and expose_me:
            if user.id != interaction.user.id:
                await interaction.response.send_message(
                	":no_entry_sign: Just FYI, `expose_me` will only work if you're exposing yourself.",
                	ephemeral=True
                	)
                return
            qid,content,aID,aName,timestamp,karma = random_quote(None, user.id)
        elif isinstance(interaction.channel, discord.abc.PrivateChannel) and bool(user):
            qid,content,aID,aName,timestamp,karma = random_quote(None, user.id)
        elif bool(user):
            qid,content,aID,aName,timestamp,karma = random_quote(interaction.guild_id, user.id)
        elif isinstance(interaction.channel, discord.abc.PrivateChannel):
            # Discord can't support this for user apps!
            # Reason being, it cannot access the list of recipients in a channel, in a user app context
            # Which is totally fine, but I have to let the user know that they need to specify
            # who they want a quote of
            await interaction.response.send_message(
            	":no_entry_sign: You'll need to specify a user when getting quotes in a private channel.\n"
            	"This is because Discord doesn't support getting the list of users when you install the app to your account,"
            	" which is *good* because it means apps like this one can't harvest your data willy-nilly!\n"
            	"So for now, just remember to select a user you want a quote from.",
            	ephemeral=True
            	)
            return
        else:
            qid,content,aID,aName,timestamp,karma = random_quote(interaction.guild_id, None)
    except LookupError as error:
        await interaction.response.send_message(str(error), ephemeral=True)
        return
    except Exception as error:
        logger.exception(error)
        return
    
    # Is the user still in the server?
    authorObject = None
    authorAvatar = None
    try: 
        authorObject = await interaction.guild.fetch_member(aID)
    except:
        pass
        
    if bool(authorObject):
        authorAvatar = authorObject.display_avatar
    else:
        author = await sanford.fetch_user(aID)
        if author:
            aName = author.name
            authorAvatar = author.display_avatar
        else: 
            aName = rename_user(aID, "'unknown', yeah, let's go with that")
    
    quoteview = discord.Embed(
        description=format_quote(content, timestamp, authorID=aID if authorObject is not None else None, authorName=aName, format='markdown')
    )
    
    # Set avatar
    if bool(authorAvatar): quoteview.set_thumbnail(url=authorAvatar.url)
    else: quoteview.set_thumbnail(url="https://cdn.thegeneral.chat/sanford/special-avatars/sanford-quote-noicon.png")
    
    if cfg['sanford']['quoting']['voting'] == True and interaction.is_guild_integration(): quoteview.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma}. Voting is open for {qvote_timeout} minutes.")
    # Send the resulting quote
    await interaction.response.send_message(allowed_mentions=discord.AllowedMentions.none(),embed=quoteview)
    
    if cfg['sanford']['quoting']['voting'] == True and interaction.is_guild_integration():
        qmsg = await interaction.original_response()

        newkarma = await karma_helper(interaction, qid, karma)
        karmadiff = newkarma[1] - karma
        
        try:
            quoteview.set_footer(text=f"Score: {'+' if newkarma[1] > 0 else ''}{newkarma[1]} ({'went up by +{karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff > 0 else 'went down by {karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff < 0 else 'did not change'} this time).")
            update_karma(qid,newkarma[1])
            await qmsg.edit(embed=quoteview)
            await qmsg.clear_reactions()
        except Exception as error:
            quoteview.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma} (no change due to error: {error}")
            await qmsg.edit(embed=quoteview)

@quote_group.command(name="top")
@app_commands.describe(author='User whose quotes you want to see')
async def quote_topquotes(interaction: discord.Interaction, author: discord.Member=None):
    """See the top quotes of the server, or of a user"""
    await interaction.response.send_message(":no_entry_sign: Coming whenever Splatsune gets the spoons.",ephemeral=True)

@quote_group.command(name="add")
@app_commands.describe(author='User who said the quote',content='The quote itself',time='When the quote happened')
async def quote_addbyhand(interaction: discord.Interaction, author: discord.Member, content: str, time: str=datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z")):
    """Create a quote manually, eg. for things said in VOIP"""
    try:
        
        # Parse entered timestamp
        timestamp = parse(time, default=datetime.now())
        
        sql_values = (
            content,
            author.id,
            author.name,
            interaction.user.id,
            interaction.guild_id if bool(interaction.guild_id) else interaction.channel.id,
            None,
            int(datetime.timestamp(timestamp))
        )
        
        qid,karma = insert_quote(sql_values)

        logger.info("Quote saved successfully")
        logger.debug(format_quote(content, authorName=author.name, timestamp=int(datetime.timestamp(timestamp))))
        
        quote = format_quote(content, authorID=author.id, authorName=author.name, timestamp=int(datetime.timestamp(timestamp)), format='discord_embed')
        quote.add_field(name='Status',value=f'Quote saved successfully.')
        authorAvatar = author.display_avatar
        quote.set_thumbnail(url=authorAvatar.url)
        if cfg['sanford']['quoting']['voting'] == True and interaction.is_guild_integration(): quote.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma}. Voting is open for {qvote_timeout} minutes.")
        await interaction.response.send_message(
            embed=quote,
            allowed_mentions=discord.AllowedMentions.none()
            )
        
        if interaction.guild_id == 124680630075260928 and author.id not in cfg['mastodon']['exclude_users']:
            post_new_quote(content, author.id, int(datetime.timestamp(timestamp)))
            
        if cfg['sanford']['quoting']['voting'] == True and interaction.is_guild_integration():
            qmsg = await interaction.original_response()
            
            newkarma = await karma_helper(interaction, qid, karma)
            karmadiff = newkarma[1] - karma
            
            try:
                quote.set_footer(text=f"Score: {'+' if newkarma[1] > 0 else ''}{newkarma[1]} ({'went up by +{karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff > 0 else 'went down by {karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff < 0 else 'did not change'} this time).")
                update_karma(qid,newkarma[1])
                await qmsg.edit(embed=quote)
                await qmsg.clear_reactions()
            except Exception as error:
                quote.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma} (no change due to error: {error}")
                await qmsg.edit(embed=quote)
        
        con.close()
    except psycopg2.DatabaseError as error:
        await interaction.response.send_message(f'Error: SQL Failed due to:\n```{str(error.with_traceback)}```',ephemeral=True)
        logger.error("QUOTE SQL ERROR:\n" + str(error.with_traceback))
    except dateutil.parser._parser.ParserError as error:
        await interaction.response.send_message(f'Error: {error}',ephemeral=True)
        
@quote_group.command(name="lb")
async def quote_leaderboards(interaction: discord.Interaction):
    '''Quote leaderboards!'''
    leaderboard = discord.Embed(
        title=f"{interaction.guild.name} Quote Leaderboards",
        description=f"These are the rankings as of right now"
        )
    
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        port = cfg['postgresql']['port'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
    )
    cur = con.cursor()
    
    # Might take a bit, so
    await interaction.response.send_message(content=":thinking:")
        
    # Most Quotes
    try:
        cur.execute(f"SELECT count(*) as quotes, authorid FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY authorid ORDER BY quotes desc LIMIT 10")

        lb_mostquoted = cur.fetchall()
        lb_mq_list = []
        for count,author in lb_mostquoted:
            try:
                user = await sanford.fetch_user(author)
            except Exception as err:
                user = "???"
            lb_mq_list.append(f"{str(user)}: **{count}**")
            
        lb_mq_string = "\n".join(lb_mq_list)
        
        leaderboard.add_field(
            name="Top 10 Most Quoted",
            value=lb_mq_string,
            inline=False
        )
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
    
    # Most Average Karma
    try:
        cur.execute(f"SELECT avg(karma), authorid FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY authorid ORDER BY avg desc LIMIT 5")

        lb_bestkarma = cur.fetchall()
        lb_bk_list = []
        for count,author in lb_bestkarma:
            try:
                user = await sanford.fetch_user(author)
            except Exception as err:
                user = "???"
            lb_bk_list.append(f"{str(user)}: **{count:.2f}**")
            
        lb_bk_string = "\n".join(lb_bk_list)
        
        leaderboard.add_field(
            name="Top 5 Highest Average Karma",
            value=lb_bk_string,
            inline=True
        )
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
    
    # Most Karma (Total)
    try:
        cur.execute(f"SELECT (sum(karma) - count(*)) as score, authorid FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY authorid ORDER BY score desc LIMIT 5")

        lb_mostkarma = cur.fetchall()
        lb_mk_list = []
        for count,author in lb_mostkarma:
            try:
                user = await sanford.fetch_user(author)
            except Exception as err:
                user = "???"
            lb_mk_list.append(f"{str(user)}: **{count}**")
            
        lb_mk_string = "\n".join(lb_mk_list)
        
        leaderboard.add_field(
            name="Top 5 Most Karma",
            value=lb_mk_string,
            inline=True
        )
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
            
    # Most Saved
    try:
        cur.execute(f"SELECT count(*), addedby FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY addedby ORDER BY count desc LIMIT 5")

        lb_mostsaved = cur.fetchall()
        lb_ms_list = []
        for count,author in lb_mostsaved:
            try:
                user = await sanford.fetch_user(author)
            except Exception as err:
                user = "???"
            lb_ms_list.append(f"{str(user)}: **{count}**")
            
        lb_ms_string = "\n".join(lb_ms_list)
        
        leaderboard.add_field(
            name="Top 5 Most Saves",
            value=lb_ms_string,
            inline=True
        )
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
    
    await interaction.edit_original_response(content=None,embed=leaderboard)
        
sanford.tree.add_command(quote_group)

@sanford.tree.context_menu(name='Leaderboard Stats')
async def quote_save(interaction: discord.Interaction, member: discord.Member):
    con = psycopg2.connect(
        database = cfg['postgresql']['database'],
        host = cfg['postgresql']['host'],
        port= cfg['postgresql']['port'],
        user = cfg['postgresql']['user'],
        password = cfg['postgresql']['password'],
    )
    cur = con.cursor()
    
    def findIndex(l, index, value):
        for pos, t in enumerate(l):
            if t[index] == value:
                return pos
        raise ValueError("list.index(x): x not in list")
    
    # Might take a bit, so
    # await interaction.response.send_message(content=":thinking:",ephemeral=true)
        
    # Most Quotes
    try:
        cur.execute(f"SELECT count(*) as quotes, authorid FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY authorid ORDER BY quotes desc")

        lb_mostquoted = cur.fetchall()

    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
    
    # Most Average Karma
    try:
        cur.execute(f"SELECT avg(karma), authorid FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY authorid ORDER BY avg desc")

        lb_bestkarma = cur.fetchall()
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
    
    
    # Most Karma (Total)
    try:
        cur.execute(f"SELECT (sum(karma) - count(*)) as score, authorid FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY authorid ORDER BY score desc")

        lb_mostkarma = cur.fetchall()
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
            
    # Most Saved
    try:
        cur.execute(f"SELECT count(*), addedby FROM bot.quotes WHERE guild={str(interaction.guild.id)} GROUP BY addedby ORDER BY count desc")

        lb_mostsaved = cur.fetchall()
    except Exception as err:
        logger.error(err)
        await interaction.edit_original_response(content=err)
        return
    
    try:
        quoterank = lb_mostquoted[findIndex(lb_mostquoted, 1, member.id)] if findIndex(lb_mostquoted, 1, member.id) else None
    except: quoterank = None
    try: 
        karmarank = lb_bestkarma[findIndex(lb_bestkarma, 1, member.id)] if findIndex(lb_bestkarma, 1, member.id) else None
    except: karmarank = None
    try: 
        karmascore = lb_mostkarma[findIndex(lb_mostkarma, 1, member.id)] if findIndex(lb_mostkarma, 1, member.id) else None
    except: karmascore = None
    try:
        savedrank = lb_mostsaved[findIndex(lb_mostsaved, 1, member.id)] if findIndex(lb_mostsaved, 1, member.id) else None
    except: savedrank = None
    
    rankmsg = f"{member.mention} is **rank {findIndex(lb_mostquoted, 1, member.id) + 1}** with **{quoterank[0]}** quotes." if quoterank else ""
    rankmsg += f"\n{member.mention} has an *average* karma score of **{karmarank[0]:.3f}**, making them **rank {findIndex(lb_bestkarma, 1, member.id) + 1}** in karma." if karmarank else ""
    rankmsg += f"\n{member.mention} has a *total* karma score of **{karmascore[0]}**, making them **rank {findIndex(lb_mostkarma, 1, member.id) + 1}** in karma." if karmascore else ""
    rankmsg += f"\n{member.mention} has saved **{savedrank[0]} quotes**, making them **rank {findIndex(lb_mostsaved, 1, member.id) + 1}** in saved quotes." if savedrank else ""
    
    await interaction.response.send_message(content=rankmsg,ephemeral=True)

@sanford.tree.context_menu(name='Save as quote!')
async def quote_save(interaction: discord.Interaction, message: discord.Message):

    try:
        con = psycopg2.connect(
            database = cfg['postgresql']['database'],
            host = cfg['postgresql']['host'],
            port = cfg['postgresql']['port'],
            user = cfg['postgresql']['user'],
            password = cfg['postgresql']['password'],
        )
        cur = con.cursor()

        # Check for duplicates first
        cur.execute("SELECT 1 from bot.quotes WHERE msgID='" + str(message.id) + "'")
        if cur.fetchone() is not None:
            raise LookupError('This quote is already in the database.')
        con.close()

        sql_values = (
            message.content, 
            message.author.id,
            message.author.name,
            interaction.user.id,
            interaction.guild_id if bool(interaction.guild_id) else interaction.channel.id,
            message.id,
            int(datetime.timestamp(message.created_at))
            )

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
                    logger.error("TypeError somewhere in the PK check code!", error)
        
        qid,karma = insert_quote(sql_values)
        if karma == None: karma = 1

        quote = format_quote(message.content, authorID=message.author.id, timestamp=int(message.created_at.timestamp()), format='discord_embed')
        quote.add_field(name='Status',value=f'[Quote]({message.jump_url}) saved successfully.')
        
        authorAvatar = message.author.display_avatar
        quote.set_thumbnail(url=authorAvatar.url)

        logger.info("Quote saved successfully")
        logger.debug(format_quote(message.content, authorName=message.author.name, timestamp=int(message.created_at.timestamp())),)
        
        if cfg['sanford']['quoting']['voting'] == True and interaction.is_guild_integration(): quote.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma}. Voting is open for {qvote_timeout} minutes.")

        await interaction.response.send_message(
            embed=quote,
            allowed_mentions=discord.AllowedMentions.none()
            )
        
        #if interaction.guild_id == 124680630075260928 and message.author.id not in cfg['mastodon']['exclude_users']:
        #    post_new_quote(message.content, (sql_values[1] if message.webhook_id else message.author.id), int(message.created_at.timestamp()))
            
        if cfg['sanford']['quoting']['voting'] == True and interaction.is_guild_integration():
            qmsg = await interaction.original_response()
            
            newkarma = await karma_helper(interaction, qid, karma)
            karmadiff = newkarma[1] - karma
            
            try:
                quote.set_footer(text=f"Score: {'+' if newkarma[1] > 0 else ''}{newkarma[1]} ({'went up by +{karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff > 0 else 'went down by {karmadiff} pts'.format(karmadiff=karmadiff) if karmadiff < 0 else 'did not change'} this time).")
                update_karma(qid,newkarma[1])
                await qmsg.edit(embed=quote)
                await qmsg.clear_reactions()
            except Exception as error:
                quote.set_footer(text=f"Score: {'+' if karma > 0 else ''}{karma} (no change due to error: {error}")
                await qmsg.edit(embed=quote)
        

    except psycopg2.DatabaseError as error:
        await interaction.response.send_message(f'Error: SQL Failed due to:\n```{str(error)}```',ephemeral=True)
        logger.error("QUOTE SQL ERROR:")
        logger.error(error, exc_info=1)
    except LookupError as error:
        await interaction.response.send_message('Good News! This quote was already saved.',ephemeral=True)
        logger.info("Quote was already saved previously")

@sanford.event
async def on_ready():
    logger.info(f"Logged in. I am {sanford.user} (ID: {sanford.user.id})")

sanford.run(cfg['sanford']['discord_token'], log_handler=handler)
