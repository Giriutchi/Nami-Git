from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, MessageHandler, filters, CallbackQueryHandler
from telegram import ChatPermissions, Update
from telegram import ChatMember
from telegram import InputFile
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from fastapi import FastAPI
import wikipediaapi
import requests
import yt_dlp
import os
import random
import datetime
import asyncio
import re
import time
import aiohttp

# Initialize the Wikipedia API with a user agent
wiki = wikipediaapi.Wikipedia(
    language='en',
    user_agent='Nami/1.0 (glitchyboiiuwu@gmail.com)'
)

# Add dictionary
async def define_word(update: Update, context: CallbackContext) -> None:
    """Fetch and send the definition of a word using DictionaryAPI."""
    if context.args:
        word = " ".join(context.args)  # Combine all arguments into a single word
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json()
            definitions = data[0].get("meanings", [])
            if definitions:
                reply = f"Definitions for *{word.capitalize()}*:\n\n"
                for meaning in definitions:
                    pos = meaning.get("partOfSpeech", "N/A")
                    reply += f"_{pos}_:\n"  # Part of speech (e.g., noun, verb)
                    for definition in meaning.get("definitions", []):
                        reply += f"- {definition.get('definition')}\n"
                await update.message.reply_text(reply, parse_mode="Markdown")
            else:
                await update.message.reply_text(f"Sorry, no definitions found for '{word}'.")
        else:
            await update.message.reply_text(f"Error: Unable to retrieve definition for '{word}'.")
    else:
        await update.message.reply_text("Please specify a word. Usage: /define <word>")

# Define your custom commands
async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message when the user starts the bot."""
    await update.message.reply_text('Hello! I am your friendly bot. How can I assist you today?')

async def help_command(update: Update, context: CallbackContext) -> None:
    """Send a help message with bot commands."""
    await update.message.reply_text('I can help you with the following commands:\n'
                                    '/start - Welcome message\n'
                                    '/help - List of commands\n'
                                    '/Series -Get series recommendations\n'
                                    '/Anime - Get anime recommendations\n'
                                    '/download_video - Downloads a video link\n'
                                    '/Search - Search a YouTube video without a link\n'
                                    '/Music - Downloads music\n'
                                    '/Wiki - Search Wikipedia\n'
                                    '/define <word> - Get the definition of a word\n'
                                    '/TMute - Mute a user for a specified time\n'
                                    '/Unmute - Immediately unmutes a muted user\n'
                                    '/Quote - Get a random quote\n'
                                    '/Cat - Send a cat picture\n'
                                    '/Flipcoin - Flip a coin to get either heads or tails')

# AniList GraphQL API URL
ANILIST_API_URL = "https://graphql.anilist.co"

def fetch_trending_anime():
    """Fetch trending anime from AniList."""
    query = """
    query {
        Page(perPage: 10) {
            media(type: ANIME, sort: TRENDING_DESC) {
                title {
                    romaji
                    english
                }
                description
                siteUrl
                coverImage {
                    large
                }
            }
        }
    }
    """
    response = requests.post(ANILIST_API_URL, json={"query": query})
    if response.status_code == 200:
        data = response.json()
        anime_list = data['data']['Page']['media']
        return random.choice(anime_list)  # Return a random anime from the list
    else:
        return None

async def recommend_anime(query: Update, context: CallbackContext) -> None:
    """Send a random anime recommendation."""
    anime = fetch_trending_anime()
    if anime:
        title = anime["title"]["english"] or anime["title"]["romaji"]
        description = anime["description"].replace("<br>", "").replace("</br>", "")[:500]  # Clean description
        site_url = anime["siteUrl"]
        cover_image = anime["coverImage"]["large"]

        # Send anime details to the user via callback query
        await query.message.reply_photo(
            photo=cover_image,
            caption=f"**{title}**\n\n{description}\n\n[More Info]({site_url})",
            parse_mode="Markdown"
        )
    else:
        await query.message.reply_text("Couldn't fetch recommendations at the moment. Try again later.")

def fetch_random_series():
    """Fetch a random TV series from TVMaze."""
    try:
        # Fetch all series data from TVMaze (example uses top-rated shows)
        response = requests.get("https://api.tvmaze.com/shows")
        if response.status_code == 200:
            series_list = response.json()
            return random.choice(series_list)  # Pick a random series
        else:
            return None
    except Exception as e:
        print(f"Error fetching series: {e}")
        return None

# Series Recommendations
async def recommend_series(query: Update, context: CallbackContext) -> None:
    """Send a random TV series recommendation."""
    series = fetch_random_series()
    if series:
        title = series["name"]
        summary = series["summary"].replace("<p>", "").replace("</p>", "")[:500]  # Clean HTML tags
        url = series["officialSite"] or series["url"]  # Use the official site if available
        image = series["image"]["medium"] if series.get("image") else None

        # Send series details to the user via callback query
        if image:
            await query.message.reply_photo(
                photo=image,
                caption=f"**{title}**\n\n{summary}\n\n[More Info]({url})",
                parse_mode="Markdown"
            )
        else:
            await query.message.reply_text(
                f"**{title}**\n\n{summary}\n\n[More Info]({url})",
                parse_mode="Markdown"
            )
    else:
        await query.message.reply_text("Couldn't fetch series recommendations at the moment. Try again later.")

# Mute function
# Dictionary to store mute timestamps
muted_users = {}

async def mute_user(update: Update, context: CallbackContext) -> None:
    """Mute a user for a specific amount of time."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a message to mute a user.")
        return
    
    # Get the user being replied to
    user_to_mute = update.message.reply_to_message.from_user.id

    # Parse the time duration (in minutes or hours)
    if not context.args:
        await update.message.reply_text("Please specify a time duration (e.g., 10m or 1h).")
        return
    
    time_input = context.args[0].lower()
    if time_input.endswith("m"):  # Handle minutes
        duration = int(time_input[:-1]) * 60  # Convert minutes to seconds
    elif time_input.endswith("h"):  # Handle hours
        duration = int(time_input[:-1]) * 3600  # Convert hours to seconds
    else:
        await update.message.reply_text("Invalid time format. Use minutes (m) or hours (h).")
        return
    
    # Mute the user
    await update.message.chat.restrict_member(user_to_mute, permissions=ChatPermissions(can_send_messages=False))
    await update.message.reply_text(f"{update.message.reply_to_message.from_user.username} has been muted for {time_input}.")
    
    # Schedule the unmute task
    async def unmute_task():
        """Unmute the user after the specified duration."""
        await asyncio.sleep(duration)
        await update.message.chat.restrict_member(user_to_mute, permissions=ChatPermissions(can_send_messages=True))
        await update.message.reply_text(f"{update.message.reply_to_message.from_user.username} has been unmuted.")
        # Remove the user from the muted_users dictionary
        muted_users.pop(user_to_mute, None)

    # Store the task so it can be tracked
    mute_task = asyncio.create_task(unmute_task())
    muted_users[user_to_mute] = mute_task

async def unmute_user(update: Update, context: CallbackContext) -> None:
    """Unmute a user manually."""
    if not update.message.reply_to_message:
        await update.message.reply_text("Please reply to a message to unmute a user.")
        return

    # Get the user being replied to
    user_to_unmute = update.message.reply_to_message.from_user.id

    # Cancel the mute task if it exists
    if user_to_unmute in muted_users:
        muted_users[user_to_unmute].cancel()
        del muted_users[user_to_unmute]

    # Unmute the user immediately
    await update.message.chat.restrict_member(user_to_unmute, permissions=ChatPermissions(can_send_messages=True))
    await update.message.reply_text(f"{update.message.reply_to_message.from_user.username} has been unmuted.")

async def quote(update: Update, context: CallbackContext) -> None:
    """Send a random quote."""
    quotes = [
    "The only way to do great work is to love what you do. – Steve Jobs",
    "Success is not final, failure is not fatal: It is the courage to continue that counts. – Winston Churchill",
    "It always seems impossible until it's done. – Nelson Mandela",
    "Don’t watch the clock; do what it does. Keep going. – Sam Levenson",
    "In the end, we only regret the chances we didn’t take. – Lewis Carroll",
    "You don't have to be rich to be happy, but you do have to be happy to be rich. – Unknown",
    "Life is what happens when you're busy making other plans. – John Lennon",
    "The purpose of life is not to be happy. It is to be useful, to be honorable, to be compassionate, to have it make some difference that you have lived and lived well. – Ralph Waldo Emerson",
    "Don’t count the days, make the days count. – Muhammad Ali",
    "I'm not arguing, I'm just explaining why I'm right. – Unknown",
    "A day without laughter is a day wasted. – Charlie Chaplin",
    "I used to think I was indecisive, but now I’m not so sure. – Unknown",
    "Behind every great man is a woman rolling her eyes. – Jim Carrey",
    "I am not lazy, I am on energy-saving mode. – Unknown",
    "The only journey is the one within. – Rainer Maria Rilke",
    "What we think, we become. – Buddha",
    "To live is the rarest thing in the world. Most people exist, that is all. – Oscar Wilde",
    "The mind is everything. What you think you become. – Buddha",
    "We do not remember days, we remember moments. – Cesare Pavese",
    "Love is not about how many days, months, or years you’ve been together. Love is about how much you love each other every day. – Unknown",
    "Love is a friendship set to music. – Joseph Campbell",
    "The best thing to hold onto in life is each other. – Audrey Hepburn",
    "To love and be loved is to feel the sun from both sides. – David Viscott",
    "In the end, we will remember not the words of our enemies, but the silence of our friends. – Martin Luther King Jr.",
]

    selected_quote = random.choice(quotes)
    await update.message.reply_text(selected_quote)

# A dictionary to track user states
user_states = {}

async def reply_to_message(update: Update, context: CallbackContext) -> None:
    """Respond to specific messages in the group."""
    user_id = update.message.from_user.id
    text = update.message.text.lower()  # Convert message to lowercase for easier matching

    # Check if the message is replying to the bot
    if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
        # Greet the user for the first time
        if user_id not in user_states and text in ("hey", "hi"):
            user_states[user_id] = "greeted"
            await update.message.reply_text("Hey, how are you? 😊")
        elif user_states.get(user_id) == "greeted":
            if text in ("i'm good", "im good", "i am good"):
                user_states[user_id] = "good_response"
                await update.message.reply_text("Glad to hear that! 😊 What can I help you with today?")
            else:
                # Reset state if the response doesn't match expected flow
                user_states.pop(user_id, None)
        else:
            # General fallback for any unhandled state
            await update.message.reply_text("I'm here to chat! What's on your mind?")

#Random cat picture
async def send_cat_picture(update: Update, context: CallbackContext) -> None:
    """Send a random cat picture when the user uses the /cat command."""
    try:
        # Fetch a random cat image from The Cat API
        response = requests.get('https://api.thecatapi.com/v1/images/search')
        response.raise_for_status()  # Raise an error for bad responses (4xx/5xx)

        # Parse the response to get the image URL
        data = response.json()
        cat_image_url = data[0]['url']

        # Send the random cat picture
        await update.message.reply_photo(cat_image_url)
    except Exception as e:
        # Handle any errors gracefully
        await update.message.reply_text('Sorry, I couldn\'t fetch a cat picture at the moment. 😿')

#Wiki search
async def wiki_search(update: Update, context: CallbackContext) -> None:
    """Search Wikipedia and send a summary to the user."""
    if not context.args:
        await update.message.reply_text("Usage: /wiki <search term>")
        return

    # Join all arguments to form a single string (including multi-word search terms)
    search_term = ' '.join(context.args)
    
    # Handle cases where the search term contains multiple words
    page = wiki.page(search_term.strip())  # Remove any extra whitespace at the start or end

    if page.exists():
        summary = page.summary[0:1000]  # Fetch first 1000 characters
        await update.message.reply_text(
            f"<b>{page.title}</b>\n\n{summary}\n\nRead more: {page.fullurl}",
            parse_mode='HTML'  # Changed to HTML to avoid Markdown errors
        )
    else:
        await update.message.reply_text(f"No results found for '{search_term}'.")

# /Start massage
async def start(update: Update, context: CallbackContext) -> None:
    """Send a welcome message and a video when the user starts the bot."""
    
    # Get the username of the user
    user_name = update.message.from_user.username
    first_name = update.message.from_user.first_name

    # Specify the path of your video
    video_path = "Nami Git/Wanted poster of nami_converted.mp4"
    
    # Create inline buttons for different functionalities
    keyboard = [
        [
            InlineKeyboardButton("Want Help?", callback_data='help'),
        ],
        [
            InlineKeyboardButton("Anime Recommendations", callback_data='anime_recommendations'),
            InlineKeyboardButton("Series Recommendations", callback_data='series_recommendations')
        ]
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send the video with a caption
    with open(video_path, 'rb') as video_file:
        await update.message.reply_video(
            video=video_file,
            caption=(f"Hey {first_name}, I'm Nami a member of the Straw Hat Pirates! I come with alot of functions which u can see if u click the 'Want Help?' button \n\n"
            "If you ever encounter any problems, contact [Support](https://t.me/BellmereNamiSupport)."),
            parse_mode="Markdown",  # Ensure Markdown is parsed for clickable link
            reply_markup=reply_markup  # Attach the inline buttons
        )

# This function will be called when the "Want Help?" button is clicked
# Callback query handler for button clicks
async def button(update: Update, context: CallbackContext) -> None:
    """Handles button click events and sends a list of commands."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to remove the "loading" state
    
    if query.data == 'help':
        await help_command(query, context)  # Pass the query object to help_command
    elif query.data == 'anime':
        await recommend_anime(query, context)
    elif query.data == 'series':
        await recommend_series(query, context)

# Help command function
async def help_command(query, context: CallbackContext) -> None:
    """Send a help message with bot commands."""
    # Instead of using `update.message`, use `query.message` since it's a callback query
    await query.message.reply_text(
        'I can help you with the following commands:\n'
        '/start - Welcome message\n'
        '/help - List of commands\n'
        '/Series - Get series recommendations\n'
        '/Anime - Get anime recommendations\n'
        '/download_video - Downloads a video link\n'
        '/Search - Search a YouTube video without a link\n'
        '/Music - Downloads music\n'
        '/Wiki - Search Wikipedia\n'
        '/define <word> - Get the definition of a word\n'
        '/TMute - Mute a user for a specified time\n'
        '/Unmute - Immediately unmutes a muted user\n'
        '/Quote - Get a random quote\n'
        '/Cat - Send a cat picture\n'
        '/Flipcoin - Flip a coin to get either heads or tails'
    )

#Aime recommendations button handler update
async def button(update: Update, context: CallbackContext) -> None:
    """Handles button click events and sends relevant information."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to remove the "loading" state

    if query.data == 'anime_recommendations':
        await recommend_anime(query, context)  # Trigger anime recommendations when the button is pressed
    # Add other cases for other buttons like 'series_recommendations', etc.

#Series recommendations button handler update
async def button(update: Update, context: CallbackContext) -> None:
    """Handles button click events and sends relevant information."""
    query = update.callback_query
    await query.answer()  # Answer the callback query to remove the "loading" state
    if query.data == 'help':
        await help_command(query, context)  # This should call help_command when "Want Help?" is clicked
    elif query.data == 'anime_recommendations':
        await recommend_anime(query, context)  # Trigger anime recommendations
    elif query.data == 'series_recommendations':
        await recommend_series(query, context)  # Trigger series recommendations when the button is pressed
    # Add other cases for other buttons like 'help', etc.

#Any video Download
async def download_video(update: Update, context: CallbackContext) -> None:
    """Download a YouTube video and send it to the user."""
    if not context.args:
        await update.message.reply_text("Please provide a YouTube URL.\nUsage: /download_video <YouTube URL>")
        return

    video_url = ' '.join(context.args)

    try:
        # Use yt-dlp to download the video
        ydl_opts = {
            'outtmpl': 'downloads/%(title)s.%(ext)s',  # Save the video in the 'downloads' folder
            'format': 'best',  # Best quality video
        }

        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            video_file = ydl.prepare_filename(info_dict)

        # Send the video to the user
        with open(video_file, 'rb') as video:
            await update.message.reply_video(video)

        # Clean up the downloaded file
        os.remove(video_file)

    except Exception as e:
        await update.message.reply_text(f"Error downloading video: {str(e)}")

# Function to search and download music
async def search_and_download_music(update: Update, context: CallbackContext):
    try:
        # Get the query from the user's message
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Please provide a search term. Example: /search Kendrick Lamar Humble")
            return

        await update.message.reply_text(f"Searching for: {query}...")

        # yt-dlp options
        output_folder = "downloads"  # Folder to save downloads
        os.makedirs(output_folder, exist_ok=True)
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }
            ],
            'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        }

        # Perform YouTube search
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(f"ytsearch:{query}", download=True)
            video_info = search_result['entries'][0]  # Get the first result
            file_path = os.path.join(output_folder, f"{video_info['title']}.mp3")

        # Send the downloaded file
        if os.path.exists(file_path):
            await update.message.reply_audio(audio=open(file_path, 'rb'), title=video_info['title'])
            os.remove(file_path)  # Clean up after sending
        else:
            await update.message.reply_text("Download failed. Please try again.")

    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")
        raise

# Function to search and download video
async def search_and_download_video(update: Update, context: CallbackContext):
    try:
        # Extract the search query from the user's message
        query = " ".join(context.args)
        if not query:
            await update.message.reply_text("Please provide a search term. Example: /search Kendrick Lamar Humble")
            return

        await update.message.reply_text(f"Searching for: {query}...")

        # Output folder for the video
        output_folder = "downloads"
        os.makedirs(output_folder, exist_ok=True)

        # yt-dlp options for downloading video
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',  # Get the best video and audio
            'quiet': True,
            'merge_output_format': 'mp4',         # Ensure output is in MP4 format
            'outtmpl': os.path.join(output_folder, '%(title)s.%(ext)s'),
        }

        # Perform YouTube search and download
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_result = ydl.extract_info(f"ytsearch:{query}", download=True)
            video_info = search_result['entries'][0]  # First search result
            file_path = os.path.join(output_folder, f"{video_info['title']}.mp4")

        # Send the downloaded video
        if os.path.exists(file_path):
            await update.message.reply_video(video=open(file_path, 'rb'), caption=f"🎥 {video_info['title']}")
            os.remove(file_path)  # Clean up after sending
        else:
            await update.message.reply_text("Download failed. Please try again.")

    except Exception as e:
        await update.message.reply_text(f"An error occurred: {e}")
        raise

# Define the function for the 'flip a coin' command
async def flip_coin(update: Update, context: CallbackContext):
    # Simulate a coin flip using random.choice
    result = random.choice(['Heads', 'Tails'])
    user_name = update.message.from_user.first_name
    await update.message.reply_text(f"{user_name}, you flipped a coin and got: {result}! 🎉")

def main() -> None:
    """Start the bot and register commands."""
    # Replace with your bot's token
    BOT_TOKEN = os.getenv("BOT_TOKEN")

    # Set up the Application object (new in v20.x)
    application = Application.builder().token(BOT_TOKEN).read_timeout(60).connect_timeout(30).build()

    # Register commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cat", send_cat_picture))
    application.add_handler(CommandHandler("wiki", wiki_search)) # Add the /wiki command
    application.add_handler(CommandHandler("download_video", download_video))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply_to_message)) #replies to specific massages
    application.add_handler(CommandHandler("quote", quote))
    application.add_handler(CommandHandler("define", define_word)) #dictionary
    application.add_handler(CommandHandler("tmute", mute_user))
    application.add_handler(CommandHandler("unmute", unmute_user))
    application.add_handler(CommandHandler("anime", recommend_anime))
    application.add_handler(CommandHandler("series", recommend_series))
    application.add_handler(CommandHandler("music", search_and_download_music))
    application.add_handler(CommandHandler("search", search_and_download_video))
    application.add_handler(CommandHandler('flipcoin', flip_coin))  # '/flipcoin' command to flip a coin
    application.add_handler(CallbackQueryHandler(button))  # This handles button clicks
   
    # Start the Bot
    application.run_polling()

if __name__ == '__main__':
    main()
