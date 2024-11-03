import os
import time
import discord
import logging
import math
import hashlib
import pymysql
import csv
import io
from discord import Member, Embed
from discord.commands import Option
from discord.commands.context import ApplicationContext
from DiscordLevelingCard import RankCard, Settings
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from datetime import datetime, timedelta
from discord.ext import commands
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
pioneer_role_id = int(os.getenv('PIONEER_ROLE_ID'))
pioneer_cert_role_id = int(os.getenv('PIONEER_CERT_ROLE_ID'))
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")

no_xp_roles = list(map(int, os.getenv('C2E_EXCLUDE_ROLE_LIST').split(',')))
no_rank_members = list(map(int, os.getenv('NO_RANK_MEMBERS').split(',')))
enabled_channel_list = list(map(int, os.getenv('C2E_ENABLED_CHANNEL_LIST').split(',')))


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/level_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, host, port, user, password, db):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=100,
            mincached=2,
            host=host,
            port=int(port),
            user=user,
            password=password,
            database=db,
            charset='utf8mb4',
            cursorclass=DictCursor
        )

    def get_connection(self):
        return self.pool.connection()


bot = commands.Bot(command_prefix=command_flag, intents=discord.Intents.all())
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)

level_2_role = None
level_5_role = None
level_10_role = None
pioneer_role = None
pioneer_cert_role = None

rank_search_users = {}


##############################
# Core Function
##############################
bulk = {
    "flag": False,
    "func": ""
}


def change_bulk(flag, func):
    global bulk
    bulk = {
        "flag": flag,
        "func": func
    }


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


def rank_to_level(org_xp: int):
    if not org_xp or org_xp < 0:
        return {
            "xp": 0,
            "level": 0,
            "total_xp": int(math.pow(2, 4))
        }

    curr_level = math.floor(math.pow(org_xp, 1/4))
    offset = 0 if curr_level == 1 else math.pow(curr_level, 4)
    xp = org_xp - offset
    xp_required = math.pow(curr_level + 1, 4) - offset

    return {
        "xp": int(xp),
        "level": curr_level - 1,
        "total_xp": int(xp_required)
    }


async def set_level_to_roles(user_id: int, level: int):
    global level_2_role, level_5_role, level_10_role, pioneer_role

    searchfi = bot.get_guild(local_server)
    user = searchfi.get_member(int(user_id))

    if level >= 10:
        await user.add_roles(level_2_role)
        await user.add_roles(level_5_role)
        await user.add_roles(level_10_role)
        logger.info(f"{user_id} -> Delete: x, Add: 2, 5, 10")
    elif 10 > level >= 5:
        await user.add_roles(level_2_role)
        await user.add_roles(level_5_role)
        await user.remove_roles(level_10_role)
        logger.info(f"{user_id} -> Delete: 10, Add: 2, 5")
    elif 5 > level >= 2:
        await user.add_roles(level_2_role)
        await user.remove_roles(level_5_role)
        await user.remove_roles(level_10_role)
        logger.info(f"{user_id} -> Delete: 5, 10, Add: 2")
    else:
        await user.remove_roles(level_2_role)
        await user.remove_roles(level_5_role)
        await user.remove_roles(level_10_role)
        logger.info(f"{user_id} -> Delete: 2, 5, 10, Add: x")


@bot.event
async def on_message(message):
    if message.author == bot.user or message.author.bot:
        return

    # 메시지가 지정된 채널 또는 역할에서 오지 않은 경우 무시
    if message.channel.id not in enabled_channel_list or any(role.id in no_xp_roles for role in message.author.roles):
        return

    user_id = message.author.id
    user_name = message.author.name
    guild_id = message.guild.id
    message_hash = hashlib.sha256(message.content.encode()).hexdigest()
    points = 0

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                select sysdate() as current_db_time
                from dual
            """)
            current_time = cursor.fetchone()['current_db_time']

            # 사용자의 마지막 메시지 정보 조회
            cursor.execute("""
                SELECT last_message_time
                FROM user_levels
                WHERE user_id = %s  AND guild_id = %s 
            """, (user_id, guild_id))
            last_message = cursor.fetchone()

            if last_message:
                cursor.execute("""
                    SELECT message_time
                    FROM user_message_logs
                    WHERE user_id = %s  AND guild_id = %s 
                    AND message_time > %s  AND message_time <= %s 
                    AND message_hash = %s
                    ORDER BY message_time DESC
                    LIMIT 1
                """, (user_id, guild_id, current_time - timedelta(seconds=120), current_time, message_hash))
                check_message = cursor.fetchone()

                # 2분 이내 동일 채팅인 경우 패스
                if not check_message:
                    # print((current_time.timestamp() - last_message['last_message_time'].timestamp()))
                    # 45초 이내 채팅인 경우 패스
                    if (current_time.timestamp() - last_message['last_message_time'].timestamp()) > 45:
                        # 메시지 필터링 및 포인트 계산 로직
                        cursor.execute("""
                            SELECT COUNT(DISTINCT message_hash) AS filtered_count
                            FROM user_message_logs
                            WHERE user_id = %s AND guild_id = %s 
                            AND message_time > %s 
                            AND message_time <= %s
                        """, (user_id, guild_id, current_time - timedelta(seconds=120), current_time))
                        filtered_result = cursor.fetchone()
                        filtered_count = filtered_result['filtered_count'] if filtered_result else 0

                        if filtered_count >= 2:
                            points = (math.sqrt(filtered_count) ** (1/3)) * 5
                        else:
                            points = 0

                        # logger.info(f"{user_name} -> {points}")

                        if points > 0:
                            cursor.execute("""
                                select xp
                                from user_levels
                                WHERE user_id = %s AND guild_id = %s
                            """, (user_id, guild_id))
                            user_level = cursor.fetchone()

                            current_xp = int(user_level['xp'])

                            cursor.execute("""
                                UPDATE user_levels
                                SET xp = xp + %s, last_message_time = %s
                                WHERE user_id = %s AND guild_id = %s
                            """, (points, current_time, user_id, guild_id))
                            connection.commit()

                            old_level = rank_to_level(current_xp)['level']
                            new_level = rank_to_level(current_xp + points)['level']

                            if old_level != new_level:
                                # LEVEL UP => role check
                                logger.info(f"{user_name} ({user_id}) LEVEL{old_level} -> LEVEL{new_level}")
                                await set_level_to_roles(user_id, new_level)

            else:
                # logger.info(f"{user_name} -> new")
                cursor.execute("""
                    INSERT INTO user_levels (user_id, guild_id, xp, last_message_time)
                    VALUES (%s, %s, %s, %s)
                """, (user_id, guild_id, points, current_time))
                connection.commit()

            cursor.execute("""
                INSERT INTO user_message_logs (user_id, guild_id, xp, message_hash, message_time)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, guild_id, points, message_hash, current_time))
            connection.commit()
    except Exception as e:
        logger.error(f"Error handling message: {e}")
        connection.rollback()
    finally:
        connection.close()

    await bot.process_commands(message)


@bot.event
async def on_ready():
    logger.info(f'{bot.user} has connected to Discord!')

    global level_2_role, level_5_role, level_10_role, pioneer_role, pioneer_cert_role

    level_2_role = bot.get_guild(local_server).get_role(level_2_role_id)
    level_5_role = bot.get_guild(local_server).get_role(level_5_role_id)
    level_10_role = bot.get_guild(local_server).get_role(level_10_role_id)
    pioneer_role = bot.get_guild(local_server).get_role(pioneer_role_id)
    pioneer_cert_role = bot.get_guild(local_server).get_role(pioneer_cert_role_id)


##############################
# Rank Commands
##############################
@bot.slash_command(
    name="rank",
    description="Show the top active users",
    guild_ids=guild_ids
)
async def get_rank(ctx: ApplicationContext,
                   user: Option(Member, "User to show rank of (Leave empty for personal rank)", required=False)):
    if not user:
        user = ctx.user

    user_name = user.name
    user_id = user.id
    guild_id = user.guild.id

    current_time = time.time()
    if rank_search_users and rank_search_users.get(user_id, None) and ctx.user.id not in no_rank_members:
        prev_time = rank_search_users.get(user_id, current_time)
        time_spent = current_time - prev_time
        doing_time = datetime.fromtimestamp(prev_time + 60*60*8)    # 8시간 딜레이 세팅
        doting_timestamp = int(doing_time.timestamp())
        if time_spent < 60*60*8:
            embed = make_embed({
                "title": "Error",
                "description": "Rank command inquiry is possible every 8 hours.\n"
                               f"Your next command query time is <t:{doting_timestamp}>",
                "color": 0xff0000,
            })
            await ctx.respond(embed=embed, ephemeral=True)
            return

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            if not user:
                user = ctx.user

            cursor.execute("""
                select user_id, xp, user_rank
                from (
                    select user_id, xp, rank() over(order by xp desc, last_message_time) as user_rank
                    from user_levels
                    where guild_id = %s
                    order by xp desc
                ) as user_ranks
                where user_id = %s
            """, (guild_id, user_id))
            data = cursor.fetchone()

            if data:
                org_xp = data['xp']
                rank = data['user_rank']
            else:
                org_xp = 0
                rank = 0

            data = rank_to_level(org_xp)

            await ctx.defer()

            card_settings = Settings(
                background="./level_card.png",
                text_color="white",
                bar_color="#ffffff"
            )

            user_level = data['level']
            user_xp = data['xp']
            user_total_xp = data['total_xp']

            rank_card = RankCard(
                settings=card_settings,
                avatar=user.display_avatar.url,
                level=user_level,
                current_exp=user_xp,
                max_exp=user_total_xp,
                username=f"{user_name}",
                rank=rank
            )
            image = await rank_card.card2()
            await ctx.respond(file=discord.File(image, filename=f"rank.png"), ephemeral=False)

            rank_search_users[user_id] = current_time
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()


@bot.slash_command(
    name="rank_leaderboard",
    description="Show the top active users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def rank_leaderboard(ctx: ApplicationContext):
    guild_id = ctx.guild.id

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            global bulk
            if bulk.get("flag"):
                embed = make_embed({
                    "title": "Warning",
                    "description": f"Bulk operation is in progress, please try again later.",
                    "color": 0xff0000,
                })
                await ctx.respond(embed=embed, ephemeral=True)
                logger.warning(f"Bulk operation is in progress, func: {bulk.get('func')}")
                return

            change_bulk(True, "rank_leaderboard")

            no_rank_members_str = ','.join([f"{member_id}" for member_id in no_rank_members])

            cursor.execute(f"""
                select user_id, xp, rank() over(order by xp desc, last_message_time) as user_rank
                from user_levels
                where guild_id = %s
                and user_id not in({no_rank_members_str})
                order by xp desc
            """, guild_id)
            db_users = cursor.fetchall()

            num_pages = (len(db_users) + 14) // 15
            pages = []
            for page in range(num_pages):
                description = ""
                for i in range(15):
                    index = page * 15 + i
                    if index >= len(db_users):
                        break
                    ranker = db_users[index]
                    user_rank = ranker['user_rank']
                    user_id = int(ranker['user_id'])
                    user = ctx.guild.get_member(user_id)
                    if user:
                        user_mention = user.mention
                    else:
                        user_mention = f"<@{user_id}>"
                    org_xp = ranker['xp']
                    rank_info = rank_to_level(org_xp)
                    user_level = rank_info['level']
                    user_xp = rank_info['xp']

                    description += f"`{user_rank}.` {user_mention} • Level **{user_level}** - **{user_xp}** XP\n"
                embed = make_embed({
                    "title": f"Leaderboard Page {page + 1}",
                    "description": description,
                    "color": 0x37e37b,
                })
                pages.append(embed)
            paginator = Paginator(pages, disable_on_timeout=False, timeout=None)
            await paginator.respond(ctx.interaction, ephemeral=False)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        change_bulk(False, "")
        connection.close()


@bot.slash_command(
    name="give_xp",
    description="Add rank XP to user",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_xp(ctx: ApplicationContext, member: Member, points: int):
    guild_id = ctx.guild.id
    user_id = member.id

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute("""
                select sysdate() as current_db_time
                from dual
            """)
            current_time = cursor.fetchone()['current_db_time']

            cursor.execute("""
                select xp
                from user_levels
                WHERE user_id = %s AND guild_id = %s
            """, (user_id, guild_id))
            user_level = cursor.fetchone()

            if user_level:
                current_xp = int(user_level['xp'])

                cursor.execute("""
                    UPDATE user_levels
                    SET xp = xp + %s, last_message_time = %s
                    WHERE user_id = %s AND guild_id = %s
                """, (points, current_time, user_id, guild_id))
            else:
                current_xp = 0

                cursor.execute("""
                    insert into user_levels (guild_id, user_id, xp, last_message_time) 
                    values (%s, %s, %s, %s)
                """, (guild_id, user_id, points, current_time))

            connection.commit()

            old_level = rank_to_level(current_xp)['level']
            new_level = rank_to_level(current_xp + points)['level']

            if old_level != new_level:
                await set_level_to_roles(user_id, new_level)

            embed = make_embed({
                "title": "XP successfully added",
                "description": f"✅ Successfully added {points} XP to {member.mention}",
                "color": 0x37e37b,
            })
            await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()


@bot.slash_command(
    name="remove_xp",
    description="Remove rank XP to user",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def remove_xp(ctx: ApplicationContext, member: Member, xp: int):
    await give_xp(ctx, member, xp*(-1))


@bot.slash_command(
    name="give_xp_bulk",
    description="Bulk add rank XP to user",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_xp_bulk(ctx: ApplicationContext,
                       file: Option(discord.Attachment, "Upload the CSV file", required=True)):
    guild_id = ctx.guild.id

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            global bulk
            if bulk.get("flag"):
                embed = make_embed({
                    "title": "Warning",
                    "description": f"Bulk operation is in progress, please try again later.",
                    "color": 0xff0000,
                })
                await ctx.respond(embed=embed, ephemeral=True)
                logger.warning(f"Bulk operation is in progress, func: {bulk.get('func')}")
                return

            change_bulk(True, "give_xp_bulk")

            file_bytes = await file.read()
            file_content = io.StringIO(file_bytes.decode('utf-8'))
            csv_reader = csv.reader(file_content, delimiter=',')

            await ctx.defer()

            cursor.execute("""
                select sysdate() as current_db_time
                from dual
            """)
            current_time = cursor.fetchone()['current_db_time']

            row_num = 1
            success_num = 0
            fail_num = 0
            for row in csv_reader:
                user_id, xp = row
                try:
                    member = ctx.guild.get_member(int(user_id))
                    if member:
                        cursor.execute("""
                            select xp
                            from user_levels
                            WHERE user_id = %s AND guild_id = %s
                        """, (user_id, guild_id))
                        user_level = cursor.fetchone()

                        if user_level:
                            current_xp = int(user_level['xp'])

                            cursor.execute("""
                                UPDATE user_levels
                                SET xp = xp + %s, last_message_time = %s
                                WHERE user_id = %s AND guild_id = %s
                            """, (int(xp), current_time, user_id, guild_id))
                            connection.commit()

                            old_level = rank_to_level(current_xp)['level']
                            new_level = rank_to_level(current_xp + int(xp))['level']

                            if old_level != new_level:
                                await set_level_to_roles(user_id, new_level)
                            await ctx.channel.send(f"🟢 Successfully added {xp} XP to {member.mention}")
                            success_num += 1
                        else:
                            # logger.info(f"{member.name} -> new")
                            cursor.execute("""
                                INSERT INTO user_levels (user_id, guild_id, xp, last_message_time)
                                VALUES (%s, %s, %s, %s)
                            """, (user_id, guild_id, int(xp), current_time))
                            connection.commit()

                            if old_level != new_level:
                                await set_level_to_roles(user_id, new_level)
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
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()
        change_bulk(False, "")


@bot.slash_command(
    name="reset_leaderboard_stats",
    description="Delete the XP stats and remove roles",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def reset_leaderboard_stats(ctx: ApplicationContext):
    guild_id = ctx.guild.id

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            await ctx.defer()

            global bulk
            if bulk.get("flag"):
                embed = make_embed({
                    "title": "Warning",
                    "description": f"Bulk operation is in progress, please try again later.",
                    "color": 0xff0000,
                })
                await ctx.respond(embed=embed, ephemeral=True)
                logger.warning(f"Bulk operation is in progress, func: {bulk.get('func')}")
                return

            change_bulk(True, "reset_leaderboard_stats")

            role_lvs = [level_2_role_id, level_5_role_id, level_10_role_id]

            cursor.execute("""
                delete from user_levels where guild_id = %s
            """, guild_id)

            cursor.execute("""
                delete from user_message_logs where guild_id = %s
            """, guild_id)

            connection.commit()

            for member in ctx.guild.members:
                for role_lv in role_lvs:
                    if member.get_role(role_lv):
                        guild_role_lv = ctx.guild.get_role(role_lv)
                        await member.remove_roles(guild_role_lv)

            embed = make_embed({
                "title": "Leaderboard Reset Completed!",
                "description": f"✅ Leaderboard have been reset successfully",
                "color": 0x37e37b,
            })
            await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()
        change_bulk(False, "")


@bot.slash_command(
    name="reset_level_role_stats",
    description="Reset level role (Using only DEV)",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.dev')
async def reset_level_role_stats(ctx: ApplicationContext):
    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            await ctx.defer()

            global bulk
            if bulk.get("flag"):
                embed = make_embed({
                    "title": "Warning",
                    "description": f"Bulk operation is in progress, please try again later.",
                    "color": 0xff0000,
                })
                await ctx.respond(embed=embed, ephemeral=True)
                logger.warning(f"Bulk operation is in progress, func: {bulk.get('func')}")
                return

            change_bulk(True, "reset_level_role_stats")

            for member in ctx.guild.members:
                user_id = member.id
                guild_id = local_server
                cursor.execute("""
                    select xp
                    from user_levels
                    WHERE user_id = %s AND guild_id = %s
                """, (user_id, guild_id))
                user_level = cursor.fetchone()

                if user_level:
                    user_level = rank_to_level(user_level['xp'])['level']
                    await set_level_to_roles(user_id, user_level)

            embed = make_embed({
                "title": "Level Role Reset Completed!",
                "description": f"✅ Level role have been reset successfully",
                "color": 0x37e37b,
            })
            await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()
        change_bulk(False, "")


@bot.slash_command(
    name="give_role_top_users",
    description="Give special role to the top 200 users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_role_top_users(ctx: ApplicationContext):
    guild_id = ctx.guild.id

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            await ctx.defer()

            global bulk
            if bulk.get("flag"):
                embed = make_embed({
                    "title": "Warning",
                    "description": f"Bulk operation is in progress, please try again later.",
                    "color": 0xff0000,
                })
                await ctx.respond(embed=embed, ephemeral=True)
                logger.warning(f"Bulk operation is in progress, func: {bulk.get('func')}")
                return

            change_bulk(True, "give_role_top_users")

            no_rank_members_str = ','.join([f"{member_id}" for member_id in no_rank_members])

            cursor.execute(f"""
                select user_id, xp, rank() over(order by xp desc, last_message_time) as user_rank
                from user_levels
                where guild_id = %s
                  and user_id not in({no_rank_members_str})
                order by xp desc
                limit 400
            """, guild_id)
            top_users = cursor.fetchall()

            # user_id와 랭킹을 딕셔너리로 변환
            top_users_dict = {str(user['user_id']): user['user_rank'] for user in top_users}

            total_members = ctx.guild.members
            logger.info(f"total_member: {len(total_members)}")

            member_index = 0
            for member in ctx.guild.members:
                if pioneer_cert_role not in member.roles:
                    member_index += 1
                    await member.remove_roles(pioneer_role)
                    logger.info(f"[reset: {member_index}]{member.name} ({member.id}) -> reset pioneer_role")

            member_index = 0
            top_200_count = 0
            for member in ctx.guild.members:
                member_index += 1
                user_rank = top_users_dict.get(str(member.id))
                if user_rank:
                    # 멤버가 파이오니아 인증 역할이 있고, 상위 200명 안에 있다면 역할 추가
                    if top_200_count < 200 and level_2_role in member.roles:
                        await member.add_roles(pioneer_role)
                        top_200_count += 1
                        logger.info(f"[{member_index}][TOP:{top_200_count}]{member.name} ({member.id}) -> Rank {user_rank} added pioneer_role")
                    else:
                        # 멤버가 상위 200명 밖이라면 역할 제거
                        logger.info(f"[{member_index}]{member.name} ({member.id}) -> Not in top 200 or no lv.2")
                else:
                    # 멤버가 상위 400명 밖이라면 역할 제거
                    logger.info(f"[{member_index}]{member.name} ({member.id}) -> Not in top 400")

            embed = make_embed({
                "title": "Top Users Refreshed!",
                "description": f"✅ Successfully Given top 200 users {pioneer_role.mention}",
                "color": 0x37e37b,
            })
            await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()
        change_bulk(False, "")


@bot.slash_command(
    name="give_role_top_users_old",
    description="Give special role to the top 200 users",
    guild_ids=guild_ids
)
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def give_role_top_users_old(ctx: ApplicationContext):
    guild_id = ctx.guild.id

    connection = db.get_connection()
    try:
        with connection.cursor() as cursor:
            await ctx.defer()

            global bulk
            if bulk.get("flag"):
                embed = make_embed({
                    "title": "Warning",
                    "description": f"Bulk operation is in progress, please try again later.",
                    "color": 0xff0000,
                })
                await ctx.respond(embed=embed, ephemeral=True)
                logger.warning(f"Bulk operation is in progress, func: {bulk.get('func')}")
                return

            change_bulk(True, "give_role_top_users")

            no_rank_members_str = ','.join([f"{member_id}" for member_id in no_rank_members])

            cursor.execute(f"""
                select user_id, xp, rank() over(order by xp desc, last_message_time) as user_rank
                from user_levels
                where guild_id = %s
                  and user_id not in({no_rank_members_str})
                order by xp desc
                limit 200
            """, guild_id)
            top_users = cursor.fetchall()

            # user_id와 랭킹을 딕셔너리로 변환
        top_users_dict = {str(user['user_id']): user['user_rank'] for user in top_users}

        pioneer_role = ctx.guild.get_role(pioneer_role_id)

        for member in ctx.guild.members:
            user_rank = top_users_dict.get(str(member.id))
            if user_rank:
                # 멤버가 상위 200명 안에 있다면 역할 추가
                if pioneer_role not in member.roles:
                    await member.add_roles(pioneer_role)
                    logger.info(f"{member.name} ({member.id}) -> Rank {user_rank} added pioneer_role")
            else:
                # 멤버가 상위 200명 밖이라면 역할 제거
                if pioneer_role in member.roles:
                    await member.remove_roles(pioneer_role)
                    logger.info(f"{member.name} ({member.id}) -> Not in top 200, removed pioneer_role")

            # await asyncio.sleep(0.2)

        embed = make_embed({
            "title": "Top Users Refreshed!",
            "description": f"✅ Successfully Given top 200 users {pioneer_role.mention}",
            "color": 0x37e37b,
        })
        await ctx.respond(embed=embed, ephemeral=False)
    except Exception as e:
        logger.error(f"An error occurred: {str(e)}")
        connection.rollback()
        embed = make_embed({
            "title": "Error",
            "description": f"An error occurred: {str(e)}",
            "color": 0xff0000,
        })
        await ctx.respond(embed=embed, ephemeral=True)
    finally:
        connection.close()
        change_bulk(False, "")

bot.run(bot_token)
