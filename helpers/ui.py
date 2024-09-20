from datetime import datetime
import psycopg2
import discord
from discord import ui

class AddedQuoteHelpers(ui.View):
    delqbutton = ui.Button(label="Delete (Quoter/Author only)", style=discord.ButtonStyle.danger)

class UpdateQuote(ui.Modal, title="Update quote details"):
    author = ui.UserSelect(custom_id='authorselect', )
    content = ui.TextInput(label="Quoted text", required=True, style=discord.TextStyle.paragraph)
    