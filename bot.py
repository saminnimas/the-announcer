from discord import (Intents,
                     Client,
                     Message)
from discord import FFmpegPCMAudio
from discord.errors import ClientException

from typing import Final, List, Tuple
import os
import json
import asyncio
from datetime import datetime, timedelta
from collections import deque

from responses import get_response


TOKEN: Final[str] = os.getenv('DISCORD_TOKEN')

MUSIC_DIR: Final[str] = "./audio"
MAPPING_FILE: Final[str] = "user_audio_map.json"
TARGET_VOICE_CHANNEL: Final[str] = "General"
INACTIVITY_TIMEOUT: Final[int] = 600  # 10 minutes in seconds
DISCONNECT_DELAY: Final[int] = 5


def load_user_audio_map() -> json:
    try:
        with open(MAPPING_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading mapping: {e}")
        return {}
    

def get_user_audio_file(member) -> str:
    try:
        with open(MAPPING_FILE, "r") as f:
            user_audio_map = json.load(f)
    except Exception as e:
        print(f"Failed to load audio map: {e}")
        return

    audio_file = user_audio_map.get(str(member.id))
    if not audio_file:
        print(f"No audio assigned for user {member.display_name}")
        return

    audio_path = os.path.join(MUSIC_DIR, audio_file)
    if not os.path.isfile(audio_path):
        print(f"Audio file not found: {audio_path}")
        return
    
    return (audio_file, audio_path)


user_audio_map = load_user_audio_map()
disconnect_timer_task = None
disconnect_event = None
    
# BOT SETUP
intents: Intents = Intents.default() # ?
intents.message_content = True
intents.voice_states = True
intents.guilds = True
intents.members = True
client: Client = Client(intents=intents) # client is the bot
# BOT SETUP


async def send_message(message: Message, user_message: str) -> None:
    if not user_message:
        print('(Message was empty because intents were not enabled probably)')
        return
    
    try:
        # Handle commands
        if user_message.startswith('/'):
            command = user_message[1:].lower().strip()  # Remove any whitespace
            print(f"Processing command: {command}")  # Debug log
            
            if command == 'a_join':
                # Find the target voice channel
                target_channel = next((vc for vc in message.guild.voice_channels if vc.name == TARGET_VOICE_CHANNEL), None)
                if target_channel:
                    try:
                        print(f"Attempting to join channel: {target_channel.name}")  # Debug log
                        await voice_manager.force_join(target_channel)
                        await message.channel.send("Bot has joined the voice channel!")
                    except Exception as e:
                        print(f"Error joining voice channel: {e}")  # Debug log
                        await message.channel.send(f"Failed to join voice channel: {e}")
                else:
                    print(f"Could not find channel: {TARGET_VOICE_CHANNEL}")  # Debug log
                    await message.channel.send(f"Could not find voice channel: {TARGET_VOICE_CHANNEL}")
                return
            elif command == 'a_leave':
                await voice_manager.force_leave()
                await message.channel.send("Bot has left the voice channel!")
                return
        
        # Handle other messages
        is_private = user_message[0] == '?'
        prompt_bot = user_message[0] == '/'
        
        if is_private or prompt_bot:
            user_message = user_message[1:]
            response: str = get_response(user_message)
            if is_private:
                await message.author.send(response)
            elif prompt_bot: 
                await message.channel.send(response)
    except Exception as e:
        print(f"Error in send_message: {e}")
        await message.channel.send("An error occurred while processing your command.")


class VoiceChannelManager:
    def __init__(self):
        self.last_activity = datetime.now()
        self.inactivity_check_task = None
        self.voice_client = None
        self.is_connected = False
        self.audio_queue = deque()
        self.is_playing = False
        self.force_connected = False

    async def start_inactivity_check(self):
        while True:
            await asyncio.sleep(60)  # Check every minute
            if self.is_connected and not self.force_connected and (datetime.now() - self.last_activity).total_seconds() > INACTIVITY_TIMEOUT:
                await self.disconnect()

    async def connect(self, channel):
        try:
            print(f"Attempting to connect to channel: {channel.name}")  # Debug log
            if self.is_connected:
                print("Already connected, disconnecting first...")  # Debug log
                await self.disconnect()
            
            self.voice_client = await channel.connect()
            self.is_connected = True
            self.last_activity = datetime.now()
            if not self.inactivity_check_task:
                self.inactivity_check_task = asyncio.create_task(self.start_inactivity_check())
            print(f"[Bot] Successfully connected to {channel.name}")
        except Exception as e:
            print(f"Error connecting to voice channel: {e}")
            self.is_connected = False
            self.voice_client = None
            raise

    async def disconnect(self):
        if self.is_connected and self.voice_client:
            try:
                print("Disconnecting from voice channel...")  # Debug log
                self.audio_queue.clear()  # Clear any pending audio
                self.is_playing = False
                await self.voice_client.disconnect()
                print("[Bot] Successfully disconnected from voice channel")
            except Exception as e:
                print(f"Error disconnecting: {e}")
            finally:
                self.is_connected = False
                self.voice_client = None
                self.force_connected = False

    def update_activity(self):
        self.last_activity = datetime.now()

    async def force_join(self, channel):
        """Force the bot to join and stay in the voice channel"""
        print(f"Force joining channel: {channel.name}")  # Debug log
        self.force_connected = True
        await self.connect(channel)

    async def force_leave(self):
        """Force the bot to leave the voice channel"""
        print("Force leaving voice channel")  # Debug log
        self.force_connected = False
        await self.disconnect()

    async def play_audio(self, audio_file: str, audio_path: str, user_name: str):
        """Add audio to queue and start playing if not already playing"""
        self.audio_queue.append((audio_file, audio_path, user_name))
        if not self.is_playing:
            await self._process_queue()

    async def _process_queue(self):
        """Process the audio queue"""
        if not self.audio_queue or self.is_playing:
            return

        self.is_playing = True
        while self.audio_queue and self.is_connected:
            try:
                audio_file, audio_path, user_name = self.audio_queue[0]
                print(f"Playing {audio_file} for {user_name}")
                
                audio_source = FFmpegPCMAudio(audio_path, executable="D:/discord_bots/requireds/ffmpeg/ffmpeg.exe")
                self.voice_client.play(audio_source)
                
                # Wait until the audio finishes
                while self.voice_client.is_playing():
                    await asyncio.sleep(0.5)
                
                # Remove the played audio from queue
                self.audio_queue.popleft()
                
            except ClientException as e:
                print(f"Error playing audio: {e}")
                # If there's an error, remove the problematic audio and continue with the queue
                if self.audio_queue:
                    self.audio_queue.popleft()
                continue
            except Exception as e:
                print(f"Unexpected error: {e}")
                if self.audio_queue:
                    self.audio_queue.popleft()
                continue

        self.is_playing = False

voice_manager = VoiceChannelManager()

@client.event
async def on_ready() -> None:
    print(f'{client.user} is now running!')
    # Connect to the target channel on startup
    for guild in client.guilds:
        target_channel = next((vc for vc in guild.voice_channels if vc.name == TARGET_VOICE_CHANNEL), None)
        if target_channel:
            await voice_manager.connect(target_channel)
            break

@client.event
async def on_message(message: Message) -> None:
    if message.author == client.user:  # so that bot doesn't keep sending itself messages
        return
    
    username: str = str(message.author)
    user_message: str = message.content
    channel: str = str(message.channel)

    print(f'[{channel}] {username}: "{user_message}"')
    
    # Process commands directly
    if user_message.startswith('/'):
        await send_message(message, user_message)
    else:
        await send_message(message, user_message)

@client.event
async def on_voice_state_update(user, before, after):
    if user.bot:
        return

    guild = user.guild
    target_channel = next((vc for vc in guild.voice_channels if vc.name == TARGET_VOICE_CHANNEL), None)
    
    if not target_channel:
        return

    # User joined the target voice channel
    if before.channel != after.channel and after.channel and after.channel.name == TARGET_VOICE_CHANNEL:
        try:
            # Ensure bot is connected
            if not voice_manager.is_connected:
                await voice_manager.connect(after.channel)
            
            voice_manager.update_activity()
            audio_file, audio_path = get_user_audio_file(user)
            
            if audio_file and audio_path:
                await voice_manager.play_audio(audio_file, audio_path, user.display_name)
        except Exception as e:
            print(f"Error in voice state update: {e}")
            # Try to recover the connection
            if not voice_manager.is_connected:
                try:
                    await voice_manager.connect(after.channel)
                except Exception as e:
                    print(f"Failed to recover connection: {e}")

    # User left the target voice channel
    elif before.channel and before.channel.name == TARGET_VOICE_CHANNEL:
        # Check if there are any non-bot users left in the channel
        remaining_users = [m for m in before.channel.members if not m.bot]
        if not remaining_users and not voice_manager.force_connected:
            voice_manager.update_activity()  # This will start the inactivity timer


def main() -> None:
    client.run(token=TOKEN)


if __name__ == '__main__':
    main()