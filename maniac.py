import discord
import os
import asyncio
import yt_dlp
from dotenv import load_dotenv

def run_bot():
    load_dotenv()
    TOKEN = os.getenv('discord_token')
    intents = discord.Intents.default()
    intents.message_content = True
    client = discord.Client(intents=intents)

    # Data structures for queues, voice clients, and volumes
    queues = {}
    voice_clients = {}
    volumes = {}

    yt_dl_options = {"format": "bestaudio/best"}
    ytdl = yt_dlp.YoutubeDL(yt_dl_options)

    # Base FFmpeg options (using reconnect flags)
    ffmpeg_base_options = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'
    }

    @client.event
    async def on_ready():
        print(f'{client.user} is now jamming')

    # This function is no longer an event; it is a helper to play the next song
    async def play_next(guild_id):
        if queues.get(guild_id):
            next_song = queues[guild_id].pop(0)
            current_volume = volumes.get(guild_id, 0.25)
            ffmpeg_options = {
                **ffmpeg_base_options,
                'options': f'-vn -filter:a "volume={current_volume}"'
            }
            player = discord.FFmpegOpusAudio(next_song['url'], **ffmpeg_options)

            # Define a callback to be called after the song finishes
            def after_playing(error):
                if error:
                    print(f"Error during playback: {error}")
                # Schedule the next song to play
                fut = asyncio.run_coroutine_threadsafe(play_next(guild_id), client.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"Error in play_next: {e}")

            if guild_id in voice_clients:
                voice_clients[guild_id].play(player, after=after_playing)
            else:
                print("No voice client available for guild", guild_id)

    @client.event
    async def on_message(message):
        # Avoid responding to the bot's own messages
        if message.author == client.user:
            return

        # Helper to get song info from a URL using yt_dlp
        async def get_song_info(url):
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=False))
            # In case of a playlist, just grab the first entry
            if 'entries' in data:
                data = data['entries'][0]
            return {'url': data['url'], 'title': data['title']}

        # Command: ?addtolist
        if message.content.startswith("?addtolist"):
            try:
                # Check that the user is in a voice channel
                if not message.author.voice or not message.author.voice.channel:
                    await message.channel.send("You need to join a voice channel first!")
                    return

                url = message.content.split()[1]
                song = await get_song_info(url)
                guild_id = message.guild.id

                queues.setdefault(guild_id, []).append(song)

                # If the bot is not connected or nothing is playing, join and start playback
                if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
                    vc = await message.author.voice.channel.connect()
                    voice_clients[guild_id] = vc
                    await play_next(guild_id)
                elif not voice_clients[guild_id].is_playing():
                    await play_next(guild_id)

                await message.channel.send(f"Added to queue: {song['title']}")
            except Exception as e:
                print(e)
                await message.channel.send("An error occurred while adding the song.")

        # Command: ?playnext (skips to the next song)
        if message.content.startswith("?playnext"):
            guild_id = message.guild.id
            if guild_id in voice_clients and queues.get(guild_id):
                voice_clients[guild_id].stop()
                await message.channel.send("Skipping to the next song in the queue")

        # Command: ?removesong (removes the first song from the queue)
        if message.content.startswith("?removesong"):
            guild_id = message.guild.id
            if queues.get(guild_id) and len(queues[guild_id]) > 0:
                removed = queues[guild_id].pop(0)
                await message.channel.send(f"Removed from queue: {removed['title']}")
            else:
                await message.channel.send("Queue is empty.")

        # Command: ?volumeup (increase volume)
        if message.content.startswith("?volumeup"):
            guild_id = message.guild.id
            current = volumes.get(guild_id, 0.25)
            new_vol = min(1.0, round(current + 0.1, 2))
            volumes[guild_id] = new_vol
            await message.channel.send(f"Volume increased to {int(new_vol*100)}%")

        # Command: ?volumedown (decrease volume)
        if message.content.startswith("?volumedown"):
            guild_id = message.guild.id
            current = volumes.get(guild_id, 0.25)
            new_vol = max(0.0, round(current - 0.1, 2))
            volumes[guild_id] = new_vol
            await message.channel.send(f"Volume decreased to {int(new_vol*100)}%")

        # Command: ?play (play a new song immediately)
        if message.content.startswith("?play"):
            try:
                if not message.author.voice or not message.author.voice.channel:
                    await message.channel.send("You need to join a voice channel first!")
                    return

                url = message.content.split()[1]
                song = await get_song_info(url)
                guild_id = message.guild.id

                # Clear the existing queue and start with this song
                queues[guild_id] = [song]

                if guild_id not in voice_clients or not voice_clients[guild_id].is_connected():
                    vc = await message.author.voice.channel.connect()
                    voice_clients[guild_id] = vc

                await play_next(guild_id)
                await message.channel.send(f"Now playing: {song['title']}")
            except Exception as e:
                print(e)
                await message.channel.send("An error occurred while trying to play the song.")

        # Command: ?pause (pause playback)
        if message.content.startswith("?pause"):
            try:
                voice_clients[message.guild.id].pause()
            except Exception as e:
                print(e)
                await message.channel.send("An error occurred while trying to pause.")

        # Command: ?resume (resume playback)
        if message.content.startswith("?resume"):
            try:
                voice_clients[message.guild.id].resume()
            except Exception as e:
                print(e)
                await message.channel.send("An error occurred while trying to resume.")

        # Command: ?stop (stop playback and disconnect)
        if message.content.startswith("?stop"):
            try:
                guild_id = message.guild.id
                if guild_id in voice_clients:
                    voice_clients[guild_id].stop()
                    await voice_clients[guild_id].disconnect()
                    del voice_clients[guild_id]
                if guild_id in queues:
                    del queues[guild_id]
                await message.channel.send("Playback stopped and disconnected from the voice channel.")
            except Exception as e:
                print(e)
                await message.channel.send("An error occurred while trying to stop.")

    client.run(TOKEN)

if __name__ == "__main__":
    run_bot()

