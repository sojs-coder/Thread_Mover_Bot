import discord
from discord.ext import commands
from discord.commands import Option
import os

map = {
    "public":discord.ChannelType.public_thread,
    "private":discord.ChannelType.private_thread
}
print(discord.__version__)
def sSort(m):
    return m.created_at

TOKEN = os.environ.get("TOKEN")

intents = discord.Intents.all()
bot = discord.Bot(command_prefix="!", intents=intents)

@bot.slash_command(description="Move messages to threads")
async def move(ctx, num_messages: int, thread_name: str, silent: Option(str, "Should I respond on success?", choices=["silent","loud"], required=False, defualt="loud"),privacy: Option(str, "Is the thread public or private?",choices=["private","public"], required=False, defualt="public")):
    # Acknowledge the command immediately
    await ctx.defer()
    
    # Get the last num_messages messages from the channel
    messages = []
    thread_name = thread_name.lower()
    async for message in ctx.channel.history(limit=num_messages):
        if message.author != bot.user:
            messages.append(message)
        
    threadExists = False
    for thread in ctx.guild.threads:
        if thread.name.lower() == thread_name.lower():
            threadExists = thread

    # Delete the last num_messages messages from the channel
    finalMessageList = messages #existingMessages + messages
    finalMessageList.sort(key=sSort)

    # Create a new thread
    thread = False
    if threadExists:
        thread = threadExists
    else:
        if privacy == "public":
            whatsUp = await ctx.send("Creating thread "+thread_name+" and moving "+ str(num_messages))
            thread = await whatsUp.create_thread(name=thread_name)
        else:
            thread = await ctx.channel.create_thread(name=thread_name)
# Move the messages to the new thread
    for message in finalMessageList:
        content = message.author.mention + " said: \n" + message.content
        await thread.send(content=content,files=[await f.to_file() for f in message.attachments])
    await ctx.channel.delete_messages(messages)
    
    if silent == "loud":
      await ctx.respond(str(num_messages) + " moved to " + thread_name)
    
# Deploy a flask server to comply with Render's requirements
if __name__ == "__main__":  
    bot.run(TOKEN)
