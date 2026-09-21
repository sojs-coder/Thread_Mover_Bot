import discord
from discord.ext import commands
import os
import asyncio
from datetime import datetime, timezone

print(f"Discord.py version: {discord.__version__}")

TOKEN = os.environ.get("TOKEN")

# Intents including message_content for reading message content
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content
intents.guilds = True  # Required for guild/channel operations

bot = discord.Bot(intents=intents)

def sort_by_creation_time(message):
    """Sort messages by creation time"""
    return message.created_at

@bot.slash_command(description="Move recent messages to a thread")
async def move(
    ctx: discord.ApplicationContext,
    num_messages: discord.Option(int, "Number of messages to move", min_value=1, max_value=100),
    thread_name: discord.Option(str, "Name for the thread"),
    visibility: discord.Option(str, "Who can see the bot's response?", choices=["private", "public"], default="public"),
    thread_privacy: discord.Option(str, "Thread visibility", choices=["private", "public"], default="public")
):
    """Move recent messages to a thread"""
    
    # Check permissions
    if not ctx.channel.permissions_for(ctx.guild.me).manage_messages:
        return await ctx.respond("❌ I need 'Manage Messages' permission to delete messages.", ephemeral=True)
    
    if not ctx.channel.permissions_for(ctx.guild.me).create_public_threads:
        return await ctx.respond("❌ I need 'Create Public Threads' permission.", ephemeral=True)
    
    if thread_privacy == "private" and not ctx.channel.permissions_for(ctx.guild.me).create_private_threads:
        return await ctx.respond("❌ I need 'Create Private Threads' permission for private threads.", ephemeral=True)

    try:
        # Determine if response should be ephemeral (private)
        is_ephemeral = (visibility == "private")
        
        # Defer response to avoid timeout
        await ctx.defer(ephemeral=is_ephemeral)
        
        # Collect messages (excluding bot messages)
        messages = []
        bot_messages_count = 0
        
        async for message in ctx.channel.history(limit=num_messages + 50):  # Get extra to account for bot messages
            if len(messages) >= num_messages:
                break
                
            if message.author.bot:
                bot_messages_count += 1
                continue
                
            messages.append(message)
        
        if not messages:
            return await ctx.followup.send("❌ No messages found to move.", ephemeral=True)
        
        # Sort messages chronologically
        messages.sort(key=sort_by_creation_time)
        
        # Check if thread already exists
        existing_thread = None
        thread_name_lower = thread_name.lower()
        
        # Check active threads
        for thread in ctx.guild.threads:
            if thread.name.lower() == thread_name_lower and not thread.archived:
                existing_thread = thread
                break
        
        # Create or use existing thread
        if existing_thread:
            thread = existing_thread
            thread_status = "Found existing thread"
        else:
            if thread_privacy == "public":
                # Create a temporary message to create public thread from
                temp_msg = await ctx.channel.send(f"📋 Creating thread: {thread_name}")
                thread = await temp_msg.create_thread(name=thread_name)
                await temp_msg.delete()  # Clean up the temporary message
            else:
                thread = await ctx.channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.private_thread
                )
            thread_status = "Created new thread"
        
        # Move messages to thread
        moved_count = 0
        moved_messages = []
        failed_moves = []
        total_attachments = 0
        successful_attachments = 0
        failed_attachments = []
        
        for message in messages:
            try:
                # Prepare content with author mention
                content_parts = [f"**{message.author.display_name}** ({message.author.mention})"]
                
                # Add timestamp
                timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
                content_parts.append(f"*{timestamp}*")
                
                # Add original content (this will now work with message_content intent)
                if message.content:
                    content_parts.append(message.content)
                else:
                    content_parts.append("*[No text content]*")
                
                content = "\n".join(content_parts)
                
                # Handle attachments
                files = []
                attachment_failed = False
                if message.attachments:
                    total_attachments += len(message.attachments)
                    for attachment in message.attachments[:10]:  # Limit to 10 attachments
                        try:
                            # Check if attachment is too large (Discord has a file size limit)
                            max_size = 25 * 1024 * 1024  # 25 MB for non-nitro servers
                            if attachment.size > max_size:
                                failed_attachments.append(f"{attachment.filename} (too large: {attachment.size / (1024*1024):.2f}MB)")
                                attachment_failed = True
                                continue

                            # Download and prepare file for re-upload
                            file = await attachment.to_file()
                            files.append(file)
                        except discord.HTTPException as e:
                            failed_attachments.append(f"{attachment.filename} (HTTP error: {str(e)})")
                            attachment_failed = True
                            print(f"Failed to copy attachment {attachment.filename}: {e}")
                        except Exception as e:
                            failed_attachments.append(f"{attachment.filename} (error: {str(e)})")
                            attachment_failed = True
                            print(f"Unexpected error copying attachment {attachment.filename}: {e}")

                if attachment_failed:
                    for file in files:
                        file.close()
                    failed_moves.append(f"Message from {message.author.display_name}: attachment copy failed")
                    continue
                
                # Handle embeds
                if message.embeds:
                    content += f"\n*[{len(message.embeds)} embed(s) from original message]*"
                
                # Send to thread
                await thread.send(content=content, files=files)
                successful_attachments += len(files)
                moved_messages.append(message)
                moved_count += 1
                
            except Exception as e:
                failed_moves.append(f"Message from {message.author.display_name}: {str(e)}")
                print(f"Failed to move message {message.id}: {e}")
        
        # Delete original messages in batches
        try:
            # Filter messages that are less than 14 days old (bulk delete limit)
            recent_messages = []
            old_messages = []
            two_weeks_ago = datetime.now(timezone.utc).timestamp() - (14 * 24 * 60 * 60)
            
            for msg in moved_messages:
                if msg.created_at.timestamp() > two_weeks_ago:
                    recent_messages.append(msg)
                else:
                    old_messages.append(msg)
            
            # Bulk delete recent messages
            if recent_messages:
                # Split into chunks of 100 (Discord's limit)
                for i in range(0, len(recent_messages), 100):
                    chunk = recent_messages[i:i+100]
                    await ctx.channel.delete_messages(chunk)
            
            # Delete old messages individually
            for msg in old_messages:
                try:
                    await msg.delete()
                    await asyncio.sleep(0.5)  # Rate limit protection
                except discord.NotFound:
                    pass  # Message already deleted
            
        except discord.Forbidden:
            await ctx.followup.send("⚠️ Messages moved but couldn't delete originals (insufficient permissions).", ephemeral=True)
        except Exception as e:
            print(f"Error deleting messages: {e}")
            await ctx.followup.send("⚠️ Messages moved but some originals couldn't be deleted.", ephemeral=True)
        
        # Prepare response message
        response_parts = [
            f"✅ {moved_count} message{'s' if moved_count != 1 else ''} moved to [{thread_name}]({thread.jump_url})",
            f"📊 {thread_status}"
        ]

        if total_attachments > 0:
            response_parts.append(f"📎 {successful_attachments}/{total_attachments} attachments moved successfully")

        if bot_messages_count > 0:
            response_parts.append(f"🤖 {bot_messages_count} bot messages ignored")

        if failed_moves:
            response_parts.append(f"⚠️ {len(failed_moves)} messages failed to move")

        if failed_attachments:
            response_parts.append(f"⚠️ {len(failed_attachments)} attachments failed to move")
        
        response = "\n".join(response_parts)
        
        # Send response (ephemeral setting already determined above)
        await ctx.followup.send(response, ephemeral=is_ephemeral)
            
    except discord.Forbidden as e:
        await ctx.followup.send(f"❌ Permission denied: {e}", ephemeral=True)
    except discord.HTTPException as e:
        await ctx.followup.send(f"❌ Discord API error: {e}", ephemeral=True)
    except Exception as e:
        await ctx.followup.send(f"❌ An unexpected error occurred: {e}", ephemeral=True)
        print(f"Unexpected error in move command: {e}")

@bot.event
async def on_ready():
    print(f"🤖 {bot.user} is ready!")
    print(f"📊 Connected to {len(bot.guilds)} guild(s)")

@bot.event
async def on_application_command_error(ctx: discord.ApplicationContext, error: discord.DiscordException):
    """Global error handler for slash commands"""
    if isinstance(error, discord.CheckFailure):
        await ctx.respond("❌ You don't have permission to use this command.", ephemeral=True)
    elif isinstance(error, discord.CommandOnCooldown):
        await ctx.respond(f"⏰ Command is on cooldown. Try again in {error.retry_after:.2f} seconds.", ephemeral=True)
    else:
        await ctx.respond("❌ An error occurred while processing the command.", ephemeral=True)
        print(f"Command error: {error}")

if __name__ == "__main__":
    bot.run(TOKEN)
