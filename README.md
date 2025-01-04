# Sanford

Sanford is a Discord bot that primarily saves messages from servers as quotes in a PostgreSQL database, and lets you get a random quote with a command. It's a Python script that uses the Discord.py library.

## Features

- Save messages as quotes
- Retrieve random quotes using commands
- Karma scoring for quotes (as a server app)
- Functions as both a server app and user app depending on your use case

## Installation

If you don't want to host your own, you can add the official Sanford bot to your account or your server using [this link](https://discord.com/oauth2/authorize?client_id=250947682758164491).

1. Clone the repository:
    ```bash
    git clone https://github.com/sflavelle/sanford.git
    cd sanford
    ```

2. Install the required dependencies:
    ```bash
    pip install -r requirements.txt
    ```

3. Set up your configuration in `config.yaml`.

4. Run the bot:
    ```bash
    python bot.py
    ```

## Commands

The main interface with the bot is the `/quote` command.
You can quickly save a message as a quote by right-clicking the message and selecting `Apps > Save as quote!`

- `/quote get` grabs a random quote from the server.
  - In DMs it will fetch quotes from anywhere.
  - Args:
    - `user` (optional) selects a user from the server to get a quote of. **Required** in DMs.
    - `all_servers` (optional) lets you get quotes from any server, **but** `user` must be yourself.
- `/quote add` lets you add a quote manually, for example if something was said in a game chat or VOIP.
  - Args:
    - `author` is the Discord user who said the quote.
    - `content` is the quote itself.
    - `time` (optional) is the date/time the quote happened. Defaults to right now.
    - `source` (optional) is an URL to whereever the quote was said, if applicable. Ideally for a Discord message link, a YouTube video, a Twitch clip, etc.
- `/quote lb` generates a leaderboard of most quoted users, who saved the most quotes, and (for server bots) highest karma and average karma.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements or bug fixes.

## License

This project is licensed under the MIT License.

## Contact

For any questions or support, please open an issue in the repository.
