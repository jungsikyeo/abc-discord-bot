import os
import discord
import pandas as pd
import logging
from discord import Embed
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
ama_vc_channel_id = int(os.getenv("AMA_VC_CHANNEL_ID"))
ama_text_channel_id = int(os.getenv("AMA_TEXT_CHANNEL_ID"))
ama_bot_log_folder = os.getenv("AMA_BOT_LOG_FOLDER")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{ama_bot_log_folder}/ama_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=f"{command_flag}", intents=intents)
message_counts = {}
ama_role_id = None
ama_in_progress = False
snapshots = []


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def start_ama(ctx, role_id: int):
    global ama_role_id, ama_in_progress
    if ama_in_progress:
        embed = Embed(title="Error",
                      description=f"❌ An AMA session is already in progress.\n\n"
                                  f"❌ AMA 세션이 이미 진행 중입니다.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    role = discord.utils.get(ctx.guild.roles, id=role_id)
    if role is None:
        embed = Embed(title="Error",
                      description=f"❌ No role found with ID: {role_id}. Please provide a valid role ID.\n\n"
                                  f"❌ {role_id} role을 찾을 수 없습니다. 올바른 role ID를 입력하십시오.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    try:
        ama_role_id = role_id
        message_counts.clear()
        snapshots.clear()
        capture_loop.start()
        ama_in_progress = True
        embed = Embed(title="Success",
                      description=f"✅ AMA session has started!\n\n"
                                  f"✅ AMA 세션이 시작되었습니다!",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def end_ama(ctx):
    global ama_role_id, ama_in_progress
    if not ama_in_progress:
        embed = Embed(title="Error",
                      description=f"❌ No AMA session is currently in progress.\n\n"
                                  f"❌ 현재 진행 중인 AMA 세션이 없습니다.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return
    try:
        capture_loop.cancel()
        await capture_final_snapshot()

        members_to_assign_role = [ctx.guild.get_member(member_id) for member_id in message_counts.keys()]
        await assign_roles(ctx, ama_role_id, members_to_assign_role)

        role_name = discord.utils.get(ctx.guild.roles, id=ama_role_id).name
        await create_and_upload_excel(ctx, snapshots, role_name)

        ama_in_progress = False

        embed = Embed(title="Success",
                      description=f"✅ AMA session has ended!\n\n"
                                  f"✅ AMA 세션이 종료되었습니다!",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.event
async def on_message(message):
    if message.channel.id == ama_text_channel_id and not message.author.bot:
        user_id = message.author.id
        if user_id in message_counts:
            message_counts[user_id] += 1
        else:
            message_counts[user_id] = 1
    await bot.process_commands(message)


@tasks.loop(minutes=20)
async def capture_loop():
    channel = bot.get_channel(ama_vc_channel_id)
    members = [member for member in channel.members if not member.bot]
    snapshot = {"Timestamp": pd.Timestamp.now()}

    for member in members:
        msg_count = message_counts.get(member.id, 0)
        snapshot[member.name] = msg_count

    logger.info(snapshot)

    snapshots.append(snapshot)


async def capture_final_snapshot():
    channel = bot.get_channel(ama_vc_channel_id)
    members = [member for member in channel.members if not member.bot]
    snapshot = {"Timestamp": pd.Timestamp.now()}
    for member in members:
        msg_count = message_counts.get(member.id, 0)
        snapshot[member.name] = msg_count
    snapshots.append(snapshot)


@bot.event
async def on_voice_state_update(member, before, after):
    if before.channel and before.channel.id == ama_vc_channel_id:
        if member.id in message_counts:
            del message_counts[member.id]


async def assign_roles(ctx, role_id, members):
    role = discord.utils.get(ctx.guild.roles, id=role_id)
    for member in members:
        try:
            await member.add_roles(role)
        except discord.Forbidden:
            embed = Embed(title="Error",
                          description=f"Failed to assign role to {member.name}. Check the bot's permissions.",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            logger.warning(f"Failed to assign role to {member.name}. Check the bot's permissions.")
        except discord.HTTPException as e:
            embed = Embed(title="Error",
                          description=f"HTTP exception while assigning role to {member.name}: {str(e)}",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            logger.warning(f"Failed to assign role to {member.name}. Check the bot's permissions.")
            logger.error(f"HTTP exception while assigning role to {member.name}: {str(e)}")


async def create_and_upload_excel(ctx, snapshots, role_name):
    file_name = f'ama_summary_{role_name}.xlsx'
    with pd.ExcelWriter(file_name, engine='xlsxwriter') as writer:
        for snapshot in snapshots:
            timestamp = snapshot["Timestamp"]
            formatted_timestamp = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            df = pd.DataFrame(list(snapshot.items())[1:], columns=['Member', 'Message_Count'])
            df.to_excel(writer, sheet_name=f'{formatted_timestamp}', index=False)
    with open(file_name, 'rb') as f:
        try:
            await ctx.reply(file=discord.File(f), mention_author=True)
            os.remove(file_name)
        except discord.HTTPException as e:
            embed = Embed(title="Error",
                          description=f"Failed to upload the file: {str(e)}",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            logger.error(f"Failed to upload the file: {str(e)}")

bot.run(bot_token)
