import discord
import pydub
import ffmpeg
import yt_dlp
from discord.ext import commands
from pydub import AudioSegment
import os
import shutil
import tempfile
import json
import random
import uuid
import subprocess
import asyncio

# Load configuration
with open('config.json') as f:
    config = json.load(f)

bot_token = config['bot_token']
messages = config['messages']
MAX_FILE_SIZE_MB = 25
SUPPORTED_FILE_TYPES = ['mp4', 'mov', 'webm', 'png', 'jpg']

# Set up bot with command prefix &ovb and cooldowns
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='&ovb ', intents=intents)

# Helper function to create a temp directory in the bot's root folder
def create_temp_dir():
    # Define the bot's root directory (the directory where the bot script is located)
    root_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Create a temp directory in the root directory
    temp_dir = os.path.join(root_dir, 'tmp')
    
    # Create the temp folder if it doesn't already exist
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
    
    # Create a unique temp subdirectory inside the 'temp' folder
    return tempfile.mkdtemp(dir=temp_dir)

# Cleanup function to remove the temp directory after use
def cleanup_temp_dir(temp_dir):
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

def get_random_message():
    return random.choice(config['messages'])

async def get_video_from_message_or_history(ctx):
    # Check if there's an attachment in the current message
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if any(attachment.filename.endswith(ext) for ext in SUPPORTED_FILE_TYPES):
            return attachment

    # If no attachment, search the channel for the last video
    async for message in ctx.channel.history(limit=50):
        if message.attachments:
            attachment = message.attachments[0]
            if any(attachment.filename.endswith(ext) for ext in SUPPORTED_FILE_TYPES):
                return attachment

    return None

# Event handler
@bot.event
async def on_ready():
    print('Bot ready!')
    
# Event to print received command
@bot.event
async def on_message(message):
    if message.content.startswith("&ovb"):
        print(f"Command: {message.content}")
    await bot.process_commands(message)

# Function to run ffmpeg command asynchronously
async def run_ffmpeg(command):
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    await process.communicate()

# Reverse video command with cooldown
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)  # Cooldown of 10 seconds per user
async def reverse(ctx):
    """Reverses the video."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    # Get the video (either from the current message or history)
    video = await get_video_from_message_or_history(ctx)
    
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    # Check file size
    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    # Save video to temp directory
    await video.save(video_path)

    # Generate a unique filename for the output to avoid conflicts
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)
    ffmpeg.input(video_path).output(output_video, vf='reverse', af='areverse').run()

    # Check size of the output video
    if os.path.getsize(output_video) > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"{user}, the edited video exceeds the {MAX_FILE_SIZE_MB} MB limit!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{user} {random_message}", file=discord.File(output_video))

    # Cleanup
    cleanup_temp_dir(temp_dir)

# Speed change command
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)  # Cooldown of 10 seconds per user
async def speed(ctx, factor: float):
    """Changes the video speed."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    # Get the video (either from the current message or history)
    video = await get_video_from_message_or_history(ctx)
    
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    # Check file size
    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    # Save video to temp directory
    await video.save(video_path)

    # Generate a unique filename for the output to avoid conflicts
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)
    ffmpeg.input(video_path).output(output_video, vf=f"setpts={1/factor}*PTS", af=f"atempo={factor}").run()

    # Check size of the output video
    if os.path.getsize(output_video) > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"{user}, the edited video exceeds the {MAX_FILE_SIZE_MB} MB limit!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{user} {random_message}", file=discord.File(output_video))

    # Cleanup
    cleanup_temp_dir(temp_dir)

# Command to change the pitch of a video/audio
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def pitch(ctx, pitch_factor: float):
    """Changes the pitch of the video/audio without affecting the speed."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    video = await get_video_from_message_or_history(ctx)
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    await video.save(video_path)

    # Generate a unique filename for the output
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)

    # Run ffmpeg to change the pitch without affecting speed
    try:
        # Use asetrate and atempo to change pitch without affecting speed
        ffmpeg.input(video_path).output(output_video, af=f'asetrate=44100*{pitch_factor},atempo=1/{pitch_factor}').run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{user} {random_message}", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

# Command to change the quality of a video
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def quality(ctx, quality: int):
    """Changes the quality of the video (1 being best, 100 being worst)."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    # Limit quality values between 1 and 100
    quality = max(1, min(quality, 100))

    # Convert to CRF value (0-51 scale for FFmpeg)
    crf_value = (quality - 1) * (51 / 99)

    video = await get_video_from_message_or_history(ctx)
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    await video.save(video_path)

    # Generate a unique filename for the output
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)

    # Run ffmpeg to change video quality
    try:
        ffmpeg.input(video_path).output(output_video, crf=crf_value).run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{user} {random_message}", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

# Command to change the volume of a video/audio
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def volume(ctx, volume_factor: float):
    """Changes the volume of the video/audio (e.g., 1.0 for normal, 0.5 for half, 2.0 for double)."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    video = await get_video_from_message_or_history(ctx)
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    await video.save(video_path)

    # Generate a unique filename for the output
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)

    # Run ffmpeg to change the volume
    try:
        ffmpeg.input(video_path).output(output_video, af=f'volume={volume_factor}').run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{user} {random_message}", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

# Command to download a YouTube video at 480p
@bot.command()
@commands.cooldown(1, 10, commands.BucketType.user)
async def download(ctx, url: str):
    """Downloads a YouTube video at 480p."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()
    
    # Set up the download options
    ydl_opts = {
        'format': 'bestvideo[height<=480]+bestaudio/best[height<=480]',  # Download video and audio at 480p
        'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),  # Save with video title
        'noplaylist': True,  # Download only the single video, not the playlist
    }

    # Download the video
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded video file
        video_filename = os.listdir(temp_dir)[0]  # Assuming only one file is downloaded
        video_path = os.path.join(temp_dir, video_filename)

        # Send the video to the Discord channel
        random_message = get_random_message()
        await ctx.reply(f"{user} {random_message}", file=discord.File(video_path))

    except Exception as e:
        print(f"yt-dlp error: {e}")
        await ctx.reply(f"{user}, something went wrong while downloading the video!")

    finally:
        cleanup_temp_dir(temp_dir)  # Clean up the temp directory

# Cooldown error handler
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"{ctx.author.mention}, please wait {round(error.retry_after, 2)} seconds before using this command again.")
    else:
        raise error

# Run the bot
bot.run(bot_token)
