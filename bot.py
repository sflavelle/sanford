# Import essential libraries
import discord
from discord import app_commands
from typing import Optional
from datetime import datetime
import yaml
# Quote-related libraries
import sqlite3
# Import custom libraries
from helpers.quoting import format_quote,fetch_random_quote
from mastoposter import post_new_quote

# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

# set variables
db = "db/quotes.sqlite"

# configure subscribed intents
intents = discord.Intents.default()
intents.message_content = True

TGC = discord.Object(id=124680630075260928)

# setup command framework
class Sanford(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        # From https://github.com/Rapptz/discord.py/blob/v2.1.0/examples/app_commands/basic.py :

        # A CommandTree is a special type that holds all the application command
        # state required to make it work. This is a separate class because it
        # allows all the extra state to be opt-in.
        # Whenever you want to work with application commands, your tree is used
        # to store and work with them.
        # Note: When using commands.Bot instead of discord.Client, the bot will
        # maintain its own tree instead.
        self.tree = app_commands.CommandTree(self)
    
    async def setup_hook(self):
        # self.tree.copy_global_to(guild=TGC) # Sync all cmds to General Chat only (for now)
        await self.tree.sync()

# init client
sanford = Sanford(intents=intents)

@sanford.event
async def on_ready():
    print("We're in B)")
    print(f"I am {sanford.user} (ID: {sanford.user.id})")
    print('------')

@sanford.tree.command()
@app_commands.guilds(TGC)
async def poke(interaction: discord.Interaction):
    """Maybe see if Sanford is around?"""
    await interaction.response.send_message('`Mhhh. Come back later...`')

@sanford.tree.command()
async def quote(interaction: discord.Interaction):
    """Get a random quote!"""
    content,aID,aName,timestamp = fetch_random_quote("db/quotes.sqlite",interaction.guild_id)

    quote = format_quote(content,authorID=aID,timestamp=timestamp)
    # Finally, send the resulting quote
    await interaction.response.send_message(quote,allowed_mentions=discord.AllowedMentions.none())

@sanford.tree.context_menu(name='Save as quote!')
async def quote_save(interaction: discord.Interaction, message: discord.Message):

    try:
        con = sqlite3.connect(db)
        cur = con.cursor()

        # Check for duplicates first
        check_dupe = cur.execute("SELECT 1 from quotes WHERE msgID='" + str(message.id) + "'")
        if check_dupe.fetchone() is not None:
            raise LookupError('This quote is already in the database.')

        sql_values = (
            message.content, 
            message.author.id,
            message.author.name,
            interaction.user.id,
            interaction.guild_id,
            message.id,
            int(datetime.timestamp(message.created_at)),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z"),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f %z")
            )
        
        cur.execute("INSERT INTO quotes (content, authorID, authorName, addedBy, guild, msgID, timestamp, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", sql_values)
        con.commit()

        status = discord.Embed(description=f'[Quote]({message.jump_url}) saved successfully.')

        await interaction.response.send_message(
            format_quote(message.content, authorID=message.author.id, timestamp=int(message.created_at.timestamp())),
            embed=status,
            allowed_mentions=discord.AllowedMentions.none()
            )
        
        if interaction.guild_id == 124680630075260928:
            post_new_quote(message.content, message.author.id, int(message.created_at.timestamp()))
        
        con.close()

    except sqlite3.Error as error:
        await interaction.response.send_message(f'Error: SQL Failed due to:\n```{str(error.with_traceback)}```',ephemeral=True)
    except LookupError as error:
        await interaction.response.send_message('Good News! This quote was already saved.',ephemeral=True)

sanford.run(cfg['sanford']['discord_token'])
