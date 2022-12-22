from datetime import datetime
import sqlite3

def format_quote(content,timestamp,authorID=None,authorName=None):
    quote_string_id = '''"{0}"
    —<@{1}> / {2}'''
    quote_string_name = '''"{0}"
    —{1} / {2}'''

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
    if bool(authorID):
        return quote_string_id.format(content,authorID,dateprint)
    elif bool(authorName) and not bool(authorID):
        return quote_string_name.format(content,authorName,dateprint)

def fetch_random_quote(db,gid):
    con = sqlite3.connect(db)
    cur = con.cursor()

    # Fetch a random quote from the SQL database
    quote = cur.execute("SELECT content,authorID,authorName,timestamp FROM quotes WHERE guild='" + str(gid) + "' AND authorID != '' ORDER BY random() LIMIT 1")
    content,aID,aName,timestamp = quote.fetchone()
    con.close()
    return (content, aID, aName, timestamp)
