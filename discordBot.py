import discord
import pydub
import ffmpeg
import yt_dlp
from discord.ext import commands
from pydub import AudioSegment
from functools import wraps
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

# Function to process multiple commands
def parse_params(message_content):
    """Extracts parameters from a command in the format param=value."""
    params = {}
    parts = message_content.split()
    
    for part in parts:
        if '=' in part:
            key, value = part.split('=', 1)
            params[key.lower()] = value
    
    return params

def get_video_duration(filepath):
    """Returns the duration of the video in seconds."""
    probe = ffmpeg.probe(filepath)
    duration = float(probe['format']['duration'])
    return duration

def generate_random_sections(duration, num_sections, min_duration=None, max_duration=None):
    """
    Generates random start and end points for sections within the given duration.
    
    :param duration: Total duration of the video.
    :param num_sections: Number of sections to generate.
    :param min_duration: Minimum duration of each section.
    :param max_duration: Maximum duration of each section.
    :return: List of tuples with start and end times for each section.
    """
    if min_duration is None:
        min_duration = 0.5  # Default min duration
    if max_duration is None:
        max_duration = 2.0  # Default max duration
    
    sections = []
    for _ in range(num_sections):
        start = random.uniform(0, duration - min_duration)
        end = min(start + random.uniform(min_duration, max_duration), duration)
        sections.append((start, end))
    return sections

# Create a decorator that adds typing indicator to commands
def with_typing():
    def decorator(func):
        @wraps(func)
        async def wrapped(ctx, *args, **kwargs):
            async with ctx.typing():  # Bot will show as typing
                return await func(ctx, *args, **kwargs)
        return wrapped
    return decorator

async def get_video_or_image_from_message_or_history(ctx):
    """Get video or image from the replied message or current message."""
    # If the command is a reply, get the original message
    if ctx.message.reference:
        referenced_message = await ctx.channel.fetch_message(ctx.message.reference.message_id)
        if referenced_message.attachments:
            return referenced_message.attachments[0]

    # Otherwise, check current message
    if ctx.message.attachments:
        return ctx.message.attachments[0]
    
    # Retrieve messages in the channel
    async for message in ctx.channel.history(limit=10):
        if message.attachments:
            return message.attachments[0]
    
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
@commands.cooldown(1, 5, commands.BucketType.channel)  # Cooldown of 10 seconds per user
@with_typing()
async def reverse(ctx):
    """Reverses the video."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    # Get the video (either from the current message or history)
    video = await get_video_or_image_from_message_or_history(ctx)

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return
    
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
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_video))

    # Cleanup
    cleanup_temp_dir(temp_dir)

# Speed change command
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)  # Cooldown of 10 seconds per user
@with_typing()
async def speed(ctx, factor: float):
    """Changes the video speed."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    # Get the video (either from the current message or history)
    video = await get_video_or_image_from_message_or_history(ctx)

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return
    
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
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_video))

    # Cleanup
    cleanup_temp_dir(temp_dir)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def pitch(ctx, pitch_value: float):
    """
    Changes the pitch of the audio in a video without affecting the speed, using the rubberband filter.
    pitch_value should be a float where:
        - A value > 1 increases the pitch (e.g., 1.5 increases by 50%)
        - A value < 1 decreases the pitch (e.g., 0.75 decreases by 25%)
    """
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    # Check if it's a video
    if not attachment.filename.endswith(('.mp4', '.mov', '.webm')):
        await ctx.reply(f"{user}, the file must be a video to adjust pitch!")
        cleanup_temp_dir(temp_dir)
        return

    file_path = os.path.join(temp_dir, attachment.filename)
    await attachment.save(file_path)

    # Set up the output file path
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_file = os.path.join(temp_dir, unique_filename)

    try:
        # Run FFmpeg with the rubberband filter for pitch shifting without speed change
        # The rubberband filter accepts a pitch shift ratio, where 1.0 is the original pitch
        # Pitch values greater than 1 increase the pitch, less than 1 decrease it
        ffmpeg.input(file_path).output(
            output_file,
            af=f"rubberband=pitch={pitch_value}"
        ).run(quiet=True, overwrite_output=True)
        
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"❌ **Error**: Something went wrong. ```{str(e)}```")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_file))

    cleanup_temp_dir(temp_dir)

# Command to change the quality of a video
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def quality(ctx, quality: int):
    """Changes the quality of the video (1 being best, 100 being worst)."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    # Limit quality values between 1 and 100
    quality = max(1, min(quality, 100))

    # Convert to CRF value (0-51 scale for FFmpeg)
    crf_value = (quality - 1) * (51 / 99)

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    video = await get_video_or_image_from_message_or_history(ctx)
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
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

# Command to change the volume of a video/audio
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def volume(ctx, volume_factor: float):
    """Changes the volume of the video/audio (e.g., 1.0 for normal, 0.5 for half, 2.0 for double)."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    video = await get_video_or_image_from_message_or_history(ctx)
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
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

# Command to download a YouTube video at 480p
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
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
        await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(video_path))

    except Exception as e:
        print(f"yt-dlp error: {e}")
        await ctx.reply(f"{user}, something went wrong while downloading the video!")

    finally:
        cleanup_temp_dir(temp_dir)  # Clean up the temp directory


@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def fps(ctx, fps_value: int):
    """Changes the frames per second of the video without changing speed."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    video = await get_video_or_image_from_message_or_history(ctx)
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    await video.save(video_path)

    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)

    # Run ffmpeg to change the FPS without changing speed
    try:
        # Using -filter:v to change the FPS
        ffmpeg.input(video_path).output(output_video, **{'vf': f'fps={fps_value}'}).run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def repu(ctx, seconds: str):
    """Repeats the video until a certain amount of seconds."""
    user = ctx.author.mention

    # Try to convert seconds to an integer
    try:
        seconds = int(seconds)
    except ValueError:
        await ctx.reply(f"{user}, please provide a valid number for seconds.")
        return

    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    video = await get_video_or_image_from_message_or_history(ctx)
    if video is None:
        await ctx.reply(f"{user}, no valid video found!")
        return

    video_path = os.path.join(temp_dir, video.filename)

    if video.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    await video.save(video_path)

    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_video = os.path.join(temp_dir, unique_filename)

    try:
        ffmpeg.input(video_path, stream_loop=-1).output(output_video, t=seconds).run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_video))

    cleanup_temp_dir(temp_dir)

# Command to change the hue of the video
@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def hue(ctx, hue_value: float):
    """Changes the hue of the image/video."""
    user = ctx.author.mention

    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    # Ensure the file is an image or video
    if not (attachment.filename.endswith(('.png', '.jpg', '.jpeg', '.mp4', '.mov', '.webm'))):
        await ctx.reply(f"{user}, please provide a valid video or image file!")
        return

    file_path = os.path.join(temp_dir, attachment.filename)

    if attachment.size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await ctx.reply(f"Error: File size exceeds {MAX_FILE_SIZE_MB} MB.")
        cleanup_temp_dir(temp_dir)
        return

    await attachment.save(file_path)

    unique_filename = f'output_{uuid.uuid4().hex}.png' if attachment.filename.endswith(('.png', '.jpg', '.jpeg')) else f'output_{uuid.uuid4().hex}.mp4'
    output_file = os.path.join(temp_dir, unique_filename)

    try:
        if attachment.filename.endswith(('.png', '.jpg', '.jpeg')):
            ffmpeg.input(file_path).output(output_file, vf=f'hue=h={hue_value}').run(quiet=True, overwrite_output=True)
        else:
            ffmpeg.input(file_path).output(output_file, vf=f'hue=h={hue_value}').run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"❌ **Error**: Something went wrong. ```{str(e)}```")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_file))

    cleanup_temp_dir(temp_dir)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def tovid(ctx):
    """Converts an image to a 10-second MP4 video. Ignores if the file is already a video."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    # Check if it's a video
    if attachment.filename.endswith(('.mp4', '.mov', '.webm')):
        await ctx.reply(f"{user}, the file is already a video!")
        cleanup_temp_dir(temp_dir)
        return

    file_path = os.path.join(temp_dir, attachment.filename)
    await attachment.save(file_path)

    # Convert image to a 10-second MP4 video
    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_file = os.path.join(temp_dir, unique_filename)

    try:
        ffmpeg.input(file_path, loop=1, t=10).output(output_file, vcodec='libx264').run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"❌ **Error**: Something went wrong. ```{str(e)}```")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_file))

    cleanup_temp_dir(temp_dir)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def togif(ctx):
    """Converts an image or video to a GIF."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None:
        await ctx.reply(f"❌ **Error**: {user}, no valid file found!")
        return

    file_path = os.path.join(temp_dir, attachment.filename)
    await attachment.save(file_path)

    # Convert to GIF
    unique_filename = f'output_{uuid.uuid4().hex}.gif'
    output_file = os.path.join(temp_dir, unique_filename)

    try:
        ffmpeg.input(file_path).output(output_file, vf="fps=10", format='gif').run(quiet=True, overwrite_output=True)
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"❌ **Error**: Something went wrong. ```{str(e)}```")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_file))

    cleanup_temp_dir(temp_dir)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def ytp(ctx):
    """Applies a 'YouTube Poop' effect: randomly reversing and un-reversing sections of a video, including the audio."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None or not attachment.filename.endswith(('.mp4', '.mov', '.webm')):
        await ctx.reply(f"{user}, no valid video file found!")
        return

    file_path = os.path.join(temp_dir, attachment.filename)
    await attachment.save(file_path)

    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_file = os.path.join(temp_dir, unique_filename)

    # Generate random reverse/unreverse points in the video
    duration = get_video_duration(file_path)  # Helper function to get the video duration using ffmpeg
    reverse_points = generate_random_sections(duration, 3)  # Generates 3 random sections for reversing

    # Construct the filter_complex for both video and audio
    filter_complex = ""
    for i, (start, end) in enumerate(reverse_points):
        filter_complex += (
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,reverse[v{i}]; "
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,areverse[a{i}]; "
        )

    # Concatenate reversed sections
    filter_complex += "".join(f"[v{i}]" for i in range(len(reverse_points))) + f"concat=n={len(reverse_points)}:v=1[outv]; "
    filter_complex += "".join(f"[a{i}]" for i in range(len(reverse_points))) + f"concat=n={len(reverse_points)}:v=0:a=1[outa]"

    try:
        # Use ffmpeg to process both video and audio
        subprocess.run(
            [
                "ffmpeg", "-i", file_path,
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "[outa]",  # Map both video and audio streams
                output_file
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_file))

    cleanup_temp_dir(temp_dir)

@bot.command()
@commands.cooldown(1, 5, commands.BucketType.channel)
@with_typing()
async def stutter(ctx):
    """Applies a stuttering effect by repeating and scrambling short chunks of the video."""
    user = ctx.author.mention
    temp_dir = create_temp_dir()

    attachment = await get_video_or_image_from_message_or_history(ctx)
    if attachment is None or not attachment.filename.endswith(('.mp4', '.mov', '.webm')):
        await ctx.reply(f"{user}, no valid video file found!")
        return

    file_path = os.path.join(temp_dir, attachment.filename)
    await attachment.save(file_path)

    unique_filename = f'output_{uuid.uuid4().hex}.mp4'
    output_file = os.path.join(temp_dir, unique_filename)

    # Get the video duration to create random sections
    duration = get_video_duration(file_path)

    # Step 1: Repeat a very short chunk (1-3 seconds)
    repeat_section = generate_random_sections(duration, 1, min_duration=1.0, max_duration=3.0)[0]

    # Step 2: Scramble very short 0.1 second chunks
    scramble_points = generate_random_sections(duration, 10, min_duration=0.1, max_duration=0.1)

    # Create filter_complex for stuttering effect
    filter_complex = (
        f"[0:v]trim=start={repeat_section[0]}:end={repeat_section[1]},setpts=PTS-STARTPTS[vrepeat]; "
        f"[0:a]atrim=start={repeat_section[0]}:end={repeat_section[1]},asetpts=PTS-STARTPTS[arepeat]; "
    )

    for i, (start, end) in enumerate(scramble_points):
        filter_complex += (
            f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[vscramble{i}]; "
            f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[ascramble{i}]; "
        )

    # Concatenate repeat section and scrambled chunks
    filter_complex += f"[vrepeat][arepeat]" + "".join(f"[vscramble{i}][ascramble{i}]" for i in range(len(scramble_points))) + f"concat=n={1+len(scramble_points)}:v=1:a=1[outv][outa]"

    try:
        # Use ffmpeg to apply the stutter effect
        subprocess.run(
            [
                "ffmpeg", "-i", file_path,
                "-filter_complex", filter_complex,
                "-map", "[outv]", "-map", "[outa]",  # Map both video and audio streams
                output_file
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"ffmpeg error: {e}")
        await ctx.reply(f"{user}, something went wrong with the video processing!")
        cleanup_temp_dir(temp_dir)
        return

    random_message = get_random_message()
    await ctx.reply(f"{random_message} || {user} [bedrock]", file=discord.File(output_file))

    cleanup_temp_dir(temp_dir)

@bot.event
async def on_command_error(ctx, error):
    # General command errors
    if isinstance(error, commands.CommandNotFound):
        await ctx.reply(f"❌ **Error**: Command not found.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(f"⏳ **Cooldown**: Please wait {round(error.retry_after, 1)} seconds.")
    else:
        # Handle general errors with better formatting
        error_message = f"❌ **Error**: An error occurred while processing your request.\n\n"
        
        # If it's an FFmpeg error, extract and show stderr if available
        if "ffmpeg error" in str(error):
            try:
                stderr_output = error.stderr.decode('utf-8')
                error_message += f"**FFmpeg Error**:\n```{stderr_output}```"
            except Exception as e:
                # If stderr is unavailable, fallback to a generic message
                error_message += f"**FFmpeg Error**: Unable to retrieve stderr output.\n\n"

        # Show the raw exception in markdown block for debugging purposes
        else:
            error_message += f"**Details**:\n```{error}```"
        
        await ctx.reply(error_message)

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandOnCooldown):
        # If the command is on cooldown, send a message with the time left
        await ctx.send(f"Cooldown! Please wait {round(error.retry_after, 2)} seconds.")
    else:
        # Handle other errors if necessary
        raise error

# Run the bot
bot.run(bot_token)
