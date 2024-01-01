import os
import discord
import logging
import csv
import io
from discord import Member, Embed
from discord.ext import commands
from discord.commands import Option
from discord.commands.context import ApplicationContext
from discordLevelingSystem import DiscordLevelingSystem, LevelUpAnnouncement, RoleAward
from DiscordLevelingCard import RankCard, Settings
from discord.ext.pages import Paginator
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("SEARCHFI_LEVEL_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
bot_log_folder = os.getenv("BOT_LOG_FOLDER")
guild_ids = list(map(int, os.getenv('GUILD_ID').split(',')))
local_server = int(os.getenv('SELF_GUILD_ID'))
local_db_file_path = os.getenv('LOCAL_DB_FILE_PATH')
local_db_file_name = os.getenv('LOCAL_DB_FILE_NAME')
level_announcement_channel_id = int(os.getenv('LEVEL_ANNOUNCEMENT_CHANNEL_ID'))
level_2_role_id = int(os.getenv('LEVEL_2_ROLE_ID'))
level_5_role_id = int(os.getenv('LEVEL_5_ROLE_ID'))
level_10_role_id = int(os.getenv('LEVEL_10_ROLE_ID'))
level_15_role_id = int(os.getenv('LEVEL_15_ROLE_ID'))
level_20_role_id = int(os.getenv('LEVEL_20_ROLE_ID'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/level_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=f"{command_flag}", intents=intents)

my_awards = {
    local_server: [
        RoleAward(role_id=level_2_role_id, level_requirement=2, role_name='LV.2_TEST'),
        RoleAward(role_id=level_5_role_id, level_requirement=5, role_name='LV.5_TEST'),
        RoleAward(role_id=level_10_role_id, level_requirement=10, role_name='LV.10_TEST'),
        RoleAward(role_id=level_15_role_id, level_requirement=15, role_name='LV.15_TEST'),
        RoleAward(role_id=level_20_role_id, level_requirement=20, role_name='LV.20_TEST'),
    ],
}

# DiscordLevelingSystem.create_database_file(rf'{local_db_file_path}')

announcement = LevelUpAnnouncement(f'{LevelUpAnnouncement.Member.mention} just leveled up to level {LevelUpAnnouncement.LEVEL} 😎',
                                   level_up_channel_ids=[level_announcement_channel_id])
lvl = DiscordLevelingSystem(awards=my_awards, level_up_announcement=announcement)
lvl.connect_to_database_file(rf'{local_db_file_path}/{local_db_file_name}')

no_xp_channels = []
no_xp_roles = list(map(int, os.getenv('C2E_EXCLUDE_ROLE_LIST').split(',')))
enabled_channel_list = list(map(int, os.getenv('C2E_ENABLED_CHANNEL_LIST').split(',')))


##############################
# Core Function
##############################
def make_embed(embed_info):
    embed = Embed(
        title=embed_info.get('title', ''),
        description=embed_info.get('description', ''),
        color=embed_info.get('color', 0xFFFFFF),
    )
    if embed_info.get('image_url', None):
        embed.set_image(
            url=embed_info.get('image_url')
        )
    embed.set_footer(text="Powered by SearchFi DEV")
    return embed


async def check_level_give_role(member: Member):
    member_level = await lvl.get_level_for(member)
    for level_role in my_awards.get(local_server):
        if level_role.level_requirement <= member_level:
            guild_level_role = bot.get_guild(local_server).get_role(level_role.role_id)
            await member.add_roles(guild_level_role)


##############################
# Core Commands
##############################
@bot.slash_command(
    name="xp_cooldown",
    description="Show the top active users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def xp_cooldown(ctx: ApplicationContext, per: int):
    try:
        await lvl.change_cooldown(1, float(per))
        embed = make_embed({
            "title": "XP Cooldown successfully setting",
            "description": f"✅ Successfully setting `{per}s` XP Cooldown",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.event
async def on_message(message):
    await lvl.award_xp(amount=15, message=message)
    await bot.process_commands(message)


@bot.event
async def on_ready():
    logger.info(f"We have logged in as {bot.user}")

    guild_id = int(os.getenv("SELF_GUILD_ID"))

    # no xp channel 세팅
    guild = bot.get_guild(guild_id)
    for channel in guild.channels:
        if channel.id in enabled_channel_list:
            continue
        no_xp_channels.append(channel.id)
    lvl.no_xp_channels = no_xp_channels


##############################
# Rank Commands
##############################
@bot.slash_command(
    name="rank",
    description="Show the top active users",
    guild_ids=guild_ids
)
async def rank(ctx: ApplicationContext,
               user: Option(Member, "User to show rank of (Leave empty for personal rank)", required=False)):
    try:
        if not user:
            user = ctx.user

        data = await lvl.get_data_for(user)

        if not data:
            await lvl.add_record(user.guild.id, user.id, user.name, 0)
            data = await lvl.get_data_for(user)

        await ctx.defer()

        card_settings = Settings(
            background="./level_card.png",
            text_color="white",
            bar_color="#ffffff"
        )

        if data and data.total_xp > 0:
            user_level = data.level
            user_xp = data.xp
            user_total_xp = lvl.get_xp_for_level(user_level+1)
        else:
            user_level = 0
            user_xp = 0
            user_total_xp = lvl.get_xp_for_level(1)

        a = RankCard(
            settings=card_settings,
            avatar=user.display_avatar.url,
            level=user_level,
            current_exp=user_xp,
            max_exp=user_total_xp,
            username=f"{user.name}"
        )
        image = await a.card2()
        await ctx.respond(file=discord.File(image, filename=f"rank.png"), ephemeral=False)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.slash_command(
    name="rank_leaderboard",
    description="Show the top active users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def rank_leaderboard(ctx: ApplicationContext):
    try:
        rankers = await lvl.each_member_data(ctx.guild, sort_by='rank')
        num_pages = (len(rankers) + 9) // 10
        pages = []
        for page in range(num_pages):
            description = ""
            for i in range(15):
                index = page * 10 + i
                if index >= len(rankers):
                    break
                ranker = rankers[index]
                description += f"`{ranker.rank}.` {ranker.mention} • Level **{ranker.level}** - **{ranker.xp}** XP\n"
            embed = make_embed({
                "title": f"Leaderboard Page {page + 1}",
                "description": description,
                "color": 0x37e37b,
            })
            pages.append(embed)
        paginator = Paginator(pages)
        await paginator.respond(ctx.interaction, ephemeral=False)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.slash_command(
    name="give_xp",
    description="Add rank XP to user",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_xp(ctx: ApplicationContext, member: Member, xp: int):
    try:
        user = lvl.get_data_for(member)
        if not user:
            await lvl.add_record(member.guild.id, member.id, member.name, 0)
        await lvl.add_xp(member, xp)

        embed = make_embed({
            "title": "XP successfully added",
            "description": f"✅ Successfully added {xp} XP to {member.mention}",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.slash_command(
    name="remove_xp",
    description="Remove rank XP to user",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def remove_xp(ctx: ApplicationContext, member: Member, xp: int):
    try:
        await lvl.remove_xp(member, xp)
        embed = make_embed({
            "title": "XP successfully removed",
            "description": f"✅ Successfully removed {xp} XP to {member.mention}",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.slash_command(
    name="give_xp_bulk",
    description="Bulk add rank XP to user",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_xp_bulk(ctx: ApplicationContext,
                       file: Option(discord.Attachment, "Upload the CSV file", required=True)):
    try:
        file_bytes = await file.read()
        file_content = io.StringIO(file_bytes.decode('utf-8'))
        csv_reader = csv.reader(file_content, delimiter=',')

        await ctx.defer()

        row_num = 1
        success_num = 0
        fail_num = 0
        for row in csv_reader:
            user_id, xp = row
            try:
                member = ctx.guild.get_member(int(user_id))
                if member:
                    await lvl.add_xp(member, int(xp))
                    await check_level_give_role(member)
                    await ctx.channel.send(f"🟢 Successfully added {xp} XP to {member.mention}")
                    success_num += 1
                else:
                    await ctx.channel.send(f"🔴 Failed to add {xp} XP to {user_id} on line {row_num}")
                    fail_num += 1
            except Exception as e:
                await ctx.channel.send(f"🔴 Failed to add {xp} XP to {user_id} on line {row_num}")
                logger.error(f"member give xp error: {str(e)}")
                fail_num += 1
            row_num += 1

        embed = make_embed({
            "title": f"Give XP to {row_num} users",
            "description": f"✅ Successfully added XP to `{success_num}` users\n"
                           f"❌ Fail added XP to `{fail_num}` users",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.slash_command(
    name="reset_leaderboard_stats",
    description="Delete the XP stats and remove roles",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def reset_leaderboard_stats(ctx: ApplicationContext):
    try:
        role_lvs = []
        for role in ctx.guild.roles:
            if "LV." in role.name:
                role_lvs.append(role.id)

        for member in ctx.guild.members:
            await lvl.reset_member(member)
            for role in member.roles:
                if "LV." in role.name:
                    await member.remove_roles(role)

        embed = make_embed({
            "title": "Leaderboard Reset Completed!",
            "description": f"✅ Leaderboard have been reset successfully",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.slash_command(
    name="give_role_top_users",
    description="Give special role to the top 200 users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_role_top_users(ctx: ApplicationContext):
    try:
        role_pioneer = None
        for role in ctx.guild.roles:
            if role.name == "SF.Pioneer":
                role_pioneer = role

        for member in ctx.guild.members:
            data = await lvl.get_data_for(member)
            if data and data.rank <= 200:
                await member.add_roles(role_pioneer)
            else:
                for role in member.roles:
                    if role == role_pioneer:
                        await member.remove_roles(role_pioneer)

        embed = make_embed({
            "title": "Top Users Refreshed!",
            "description": f"✅ Successfully Given top 200 users {role_pioneer.mention}",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
        logger.error(f"An error occurred: {str(e)}")


bot.run(bot_token)
