# Import essential libraries
import discord
from discord import app_commands
from typing import Optional
from datetime import datetime
import yaml
# Quote-related libraries
import sqlite3

# init sqlite db connection
con = sqlite3.connect("db/quotes.sqlite")
cur = con.cursor()
# load config
with open('config.yaml', 'r') as file:
    cfg = yaml.safe_load(file)

# configure subscribed intents
intents = discord.Intents.default()
intents.message_content = True

TGC = discord.Object(id=124680630075260928)

quote_string = '''"{0}"
    —<@{1}> / {2}'''

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
    
    # Sync all cmds to General Chat only (for now)
    async def setup_hook(self):
        self.tree.copy_global_to(guild=TGC)
        await self.tree.sync(guild=TGC)

# init client
sanford = Sanford(intents=intents)

@sanford.event
async def on_ready():
    print(f"We're in B) I am {sanford.user} (ID: {sanford.user.id})")
    print('------')

@sanford.tree.command()
async def poke(interaction: discord.Interaction):
    """Maybe see if Sanford is around?"""
    await interaction.response.send_message('`Mhhh. Come back later...`')

@sanford.tree.command()
async def quote(interaction: discord.Interaction):
    """Get a random quote!"""
    
    # Fetch a random quote from the SQL database
    quote = cur.execute("SELECT content,authorID,authorName,timestamp FROM quotes WHERE guild='" + str(interaction.guild.id) + "' AND authorID != '' ORDER BY random() LIMIT 1")
    content,aID,aName,timestamp = quote.fetchone()

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

    # Finally, send the resulting quote
    await interaction.response.send_message(quote_string.format(content,aID,dateprint),allowed_mentions=discord.AllowedMentions.none())

@sanford.tree.context_menu(name='Save as quote!')
async def quote_save(interaction: discord.Interaction, message: discord.Message):
    try:
        sql_values = (
            message.content, 
            message.author.id,
            message.author.name,
            interaction.user.id,
            interaction.guild_id,
            message.id,
            datetime.timestamp(message.created_at),
            datetime.now().strftime("%Y-%m-%d %H:%M::%S.%f %z"),
            datetime.now().strftime("%Y-%m-%d %H:%M::%S.%f %z")
            )
        
        cur.execute("INSERT INTO quotes (content, authorID, authorName, addedBy, guild, msgID, timestamp, createdAt, updatedAt) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);", sql_values)
        con.commit()

        await interaction.response.send_message(
            "`Quoted successfully!`\n\n"
            + quote_string.format(message.content, message.author.id, message.created_at.strftime("%B %d, %Y")),
            allowed_mentions=discord.AllowedMentions.none()
            )
    except sqlite3.Error as error:
        await interaction.response.send_message('Error: Failed due to:\n' + str(error),ephemeral=True)

sanford.run(cfg['sanford']['discord_token'])