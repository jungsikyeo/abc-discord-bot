import os
import discord
import pandas as pd
import logging
import time
import pymysql
from discord import Embed
from discord.ext import commands, tasks
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from typing import Union

load_dotenv()

bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
ama_vc_channel_id = int(os.getenv("AMA_VC_CHANNEL_ID"))
ama_text_channel_id = int(os.getenv("AMA_TEXT_CHANNEL_ID"))
ama_loop_time = int(os.getenv("AMA_LOOP_TIME"))
bot_log_folder = os.getenv("BOT_LOG_FOLDER")
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/ama_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

message_counts = {}
message_all_counts = {}
voice_join_counts = {}
voice_leave_counts = {}
voice_channel_time_spent = {}
voice_channel_join_times = {}
ama_role_id = None
ama_in_progress = False
ama_end_progress = False
snapshots = []


class Database:
    def __init__(self, host, port, user, password, db):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
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


intents = discord.Intents.all()
bot = commands.Bot(command_prefix=f"{command_flag}", intents=intents)
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)


@bot.event
async def on_ready():
    print(f"We have logged in as {bot.user}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def start_ama(ctx, role: Union[discord.Role, int, str]):
    global ama_role_id, ama_in_progress
    if ama_in_progress:
        embed = Embed(title="Error",
                      description=f"❌ AMA session is already in progress.\n\n"
                                  f"❌ AMA 세션이 이미 진행 중입니다.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    # 입력값이 롤 객체인 경우
    if isinstance(role, discord.Role):
        role_found = role
    # 입력값이 역할 ID인 경우
    elif isinstance(role, int):
        role_found = discord.utils.get(ctx.guild.roles, id=role)
    # 입력값이 역할 이름인 경우
    else:
        role_found = discord.utils.get(ctx.guild.roles, name=role)

    if role_found is None:
        embed = Embed(title="Error",
                      description=f"❌ Role not found for name, ID, or mention {role}. Please enter a valid role name, ID, or mention.\n\n"
                                  f"❌ {role} 이름, ID 또는 멘션의 역할을 찾을 수 없습니다. 올바른 역할 이름, ID 또는 멘션을 입력해주세요.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    try:
        ama_role_id = role_found.id
        snapshots.clear()
        message_counts.clear()
        message_all_counts.clear()
        voice_join_counts.clear()
        voice_leave_counts.clear()
        voice_channel_time_spent.clear()
        voice_channel_join_times.clear()
        capture_loop.start(ctx)
        # 현재 AMA 채널의 사용자 체크
        voice_channel = bot.get_channel(ama_vc_channel_id)
        current_members = voice_channel.members
        current_time = time.time()
        for member in current_members:
            if not member.bot:  # 봇 제외
                voice_join_counts[member.id] = 1
                voice_channel_join_times[member.id] = current_time  # 입장 시간 설정
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
    global ama_role_id, ama_in_progress, ama_end_progress
    if not ama_in_progress:
        embed = Embed(title="Error",
                      description=f"❌ No AMA session is currently in progress.\n\n"
                                  f"❌ 현재 진행 중인 AMA 세션이 없습니다.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    # AMA가 이미 종료 중인지 확인
    if ama_end_progress:
        embed = Embed(title="Error",
                      description=f"❌ AMA session is already ending. Please wait.\n\n"
                                  f"❌ AMA 세션이 이미 종료 중입니다. 기다려 주세요.",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        return

    ama_end_progress = True

    try:
        capture_loop.cancel()
        await capture_final_snapshot(ctx)

        members_to_assign_role = [ctx.guild.get_member(member_id) for member_id in message_counts.keys()]
        await assign_roles(ctx, ama_role_id, members_to_assign_role)

        role_name = discord.utils.get(ctx.guild.roles, id=ama_role_id).name
        await create_and_upload_excel(ctx, snapshots, role_name)

        # 데이터베이스에 데이터 저장
        db_data = []
        for member_id in voice_join_counts:
            try:
                member = ctx.guild.get_member(member_id)
                if member:  # 사용자가 여전히 서버에 있는 경우
                    member_name = member.name  # 멤버의 디스플레이 이름 가져오기
                else:  # 사용자가 서버를 떠난 경우
                    member_name = str(member_id)  # 멤버의 ID를 문자열로 사용
                    logger.warning(f"Member with ID {member_id} not found. They might have left the server.")
            except Exception as e:  # 다른 예외 처리
                member_name = "Unknown"
                logger.error(f"An error occurred while getting member info: {str(e)}")

            total_messages = message_all_counts.get(member_id, 0)
            valid_messages = message_counts.get(member_id, 0)  # 유효한 메시지 수를 여기에 입력하세요
            total_joins = voice_join_counts.get(member_id, 0)
            total_leaves = voice_leave_counts.get(member_id, 0)
            time_spent = int(voice_channel_time_spent.get(member_id, 0))  # 밀리초를 초로 변환

            db_data.append((
                str(ama_role_id), role_name, str(member_id),
                member_name,
                total_messages, valid_messages, total_joins, total_leaves, time_spent
            ))
        # 데이터베이스에 데이터 저장
        await save_data_to_db(ctx, db_data)

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

    ama_end_progress = False


async def save_snapshot_to_db(ctx, snapshot_data):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        timestamp = snapshot_data["Timestamp"]
        ama_role_name = discord.utils.get(ctx.guild.roles, id=ama_role_id).name
        for member_id, member_data in snapshot_data.items():
            if member_id != "Timestamp":  # Ensure we don't process the "Timestamp" key as a member
                cursor.execute("""
                    INSERT INTO ama_users_summary_snapshot (
                        role_id, role_name, user_id, user_name,
                        total_messages, valid_messages,
                        total_joins, total_leaves, time_spent, timestamp
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    str(ama_role_id),
                    str(ama_role_name),
                    str(member_id),
                    member_data['Member_Name'],
                    member_data['Total_Messages'],
                    member_data['Valid_Messages'],
                    member_data['Total_Joins'],
                    member_data['Total_Leaves'],
                    member_data['Total_Time_Spent_in_VC_(seconds)'],
                    timestamp
                ))

        connection.commit()

    except Exception as e:
        logger.error(f'DB error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


async def save_data_to_db(ctx, db_data):
    connection = db.get_connection()
    cursor = connection.cursor()
    try:
        for data in db_data:
            cursor.execute("""
                INSERT INTO ama_users_summary (
                    role_id,
                    role_name,
                    user_id,
                    user_name,
                    total_messages,
                    valid_messages,
                    total_joins,
                    total_leaves,
                    time_spent
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, data)

        connection.commit()

        embed = Embed(
            title='DB Save Complete',
            description="DB Save Complete!\n"
                        "Please AMA Summary by User: `!ama_info \"<AMA Role name>\" <User Tag>`",
            color=0xFFFFFF,
        )

        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        logger.error(f'DB error: {e}')
        connection.rollback()
    finally:
        cursor.close()
        connection.close()


@bot.event
async def on_message(message):
    if message.channel.id == ama_text_channel_id and not message.author.bot:
        user_id = message.author.id
        if user_id in message_counts:
            message_counts[user_id] += 1
        else:
            message_counts[user_id] = 1

        if user_id in message_all_counts:
            message_all_counts[user_id] += 1
        else:
            message_all_counts[user_id] = 1
    await bot.process_commands(message)


@tasks.loop(minutes=ama_loop_time)
async def capture_loop(ctx):
    try:
        channel = bot.get_channel(ama_vc_channel_id)
        members = [member for member in channel.members if not member.bot]
        now = pd.Timestamp.now()
        current_time = time.time()
        snapshot = {"Timestamp": now}
        for member in members:
            msg_count = message_counts.get(member.id, 0)
            all_msg_count = message_all_counts.get(member.id, 0)
            total_joins = voice_join_counts.get(member.id, 0)
            total_leaves = voice_leave_counts.get(member.id, 0)

            # time_spent 계산
            join_time = voice_channel_join_times.get(member.id, current_time)
            time_spent = current_time - join_time
            total_time_spent = voice_channel_time_spent.get(member.id, 0) + time_spent

            snapshot[member.id] = {
                "Member_Name": member.name,
                "Total_Messages": all_msg_count,
                "Valid_Messages": msg_count,
                "Total_Joins": total_joins,
                "Total_Leaves": total_leaves,
                "Total_Time_Spent_in_VC_(seconds)": total_time_spent
            }
        logger.info(snapshot)
        snapshots.append(snapshot)

        await save_snapshot_to_db(ctx, snapshot)

        embed = Embed(title="Success",
                      description=f"✅ Snapshot `{now}` has been created.\n\n"
                                  f"✅ `{now}` 스냅샷이 생성되었습니다.",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


async def capture_final_snapshot(ctx):
    try:
        channel = bot.get_channel(ama_vc_channel_id)
        members = [member for member in channel.members if not member.bot]
        now = pd.Timestamp.now()
        current_time = time.time()
        snapshot = {"Timestamp": now}
        for member in members:
            msg_count = message_counts.get(member.id, 0)
            all_msg_count = message_all_counts.get(member.id, 0)
            total_joins = voice_join_counts.get(member.id, 0)
            total_leaves = voice_leave_counts.get(member.id, 0)

            # time_spent 계산
            join_time = voice_channel_join_times.get(member.id, current_time)
            time_spent = current_time - join_time
            total_time_spent = voice_channel_time_spent.get(member.id, 0) + time_spent
            voice_channel_time_spent[member.id] = total_time_spent

            snapshot[member.id] = {
                "Member_Name": member.name,
                "Total_Messages": all_msg_count,
                "Valid_Messages": msg_count,
                "Total_Joins": total_joins,
                "Total_Leaves": total_leaves,
                "Total_Time_Spent_in_VC_(seconds)": total_time_spent
            }
        logger.info(snapshot)
        snapshots.append(snapshot)

        await save_snapshot_to_db(ctx, snapshot)

        embed = Embed(title="Success",
                      description=f"✅ Snapshot `{now}` has been created.\n"
                                  f"Soon a role will be assigned and an Excel file will be created.\n"
                                  f"Please wait a moment.\n\n"
                                  f"✅ `{now}` 스냅샷이 생성되었습니다.\n"
                                  f"곧 롤이 부여되고, 엑셀파일이 생성됩니다.\n"
                                  f"잠시만 기다려주세요.",
                      color=0x37e37b)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


@bot.event
async def on_voice_state_update(member, before, after):
    current_time = time.time()

    # 사용자가 음성 채널에 들어왔는지 확인
    if before.channel is None and after.channel is not None and after.channel.id == ama_vc_channel_id:
        if member.id in voice_join_counts:
            voice_join_counts[member.id] += 1
        else:
            voice_join_counts[member.id] = 1

        # 사용자가 채널에 들어온 시간 기록
        voice_channel_join_times[member.id] = current_time

    # 사용자가 음성 채널에서 나갔는지 확인
    if before.channel is not None and before.channel.id == ama_vc_channel_id and after.channel is None:
        if member.id in voice_leave_counts:
            voice_leave_counts[member.id] += 1
        else:
            voice_leave_counts[member.id] = 1

        # 사용자가 채널에서 나간 시간 기록 및 머무른 시간 계산
        if member.id in voice_channel_join_times:
            join_time = voice_channel_join_times[member.id]
            time_spent = current_time - join_time
            voice_channel_time_spent[member.id] = voice_channel_time_spent.get(member.id, 0) + time_spent
            # 사용자가 나간 후, join 시간 정보 삭제
            del voice_channel_join_times[member.id]

        # AMA 중에 음성 채널을 떠나면 해당 사용자의 message_counts를 제거
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
        # 스냅샷 데이터를 엑셀에 기록
        for snapshot in snapshots:
            timestamp = snapshot["Timestamp"]
            formatted_timestamp = timestamp.strftime("%Y-%m-%d_%H-%M-%S")
            df = pd.DataFrame(list(snapshot.items())[1:], columns=['Member', 'Message_Count'])
            df.to_excel(writer, sheet_name=f'{formatted_timestamp}', index=False)

        # 사용자별 통계 데이터를 포함하는 새 데이터 프레임 생성
        data = []
        for member_id in message_all_counts:
            try:
                member = ctx.guild.get_member(member_id)
                if member:  # 사용자가 여전히 서버에 있는 경우
                    member_name = member.display_name  # 멤버의 디스플레이 이름 가져오기
                else:  # 사용자가 서버를 떠난 경우
                    member_name = str(member_id)  # 멤버의 ID를 문자열로 사용
                    logger.warning(f"Member with ID {member_id} not found. They might have left the server.")
            except Exception as e:  # 다른 예외 처리
                member_name = "Unknown"
                logger.error(f"An error occurred while getting member info: {str(e)}")

            total_messages = message_all_counts.get(member_id, 0)
            total_joins = voice_join_counts.get(member_id, 0)
            total_leaves = voice_leave_counts.get(member_id, 0)
            total_time_spent = int(voice_channel_time_spent.get(member_id, 0))  # 총 시간은 초 단위로 계산됩니다.

            data.append({
                'Member_ID': member_id,
                'Member_Name': member_name,
                'Total_Messages': total_messages,
                'Total_Joins': total_joins,
                'Total_Leaves': total_leaves,
                'Total_Time_Spent_in_VC_(seconds)': total_time_spent,  # 초 단위의 시간
            })

        df_summary = pd.DataFrame(data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)  # 'Summary' 시트에 데이터 기록

    try:
        with open(file_name, 'rb') as f:
            await ctx.reply(file=discord.File(f), mention_author=True)
        os.remove(file_name)  # 파일 사용이 완료된 후 파일 삭제
    except discord.HTTPException as e:
        embed = Embed(title="Error",
                      description=f"Failed to upload the file: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"Failed to upload the file: {str(e)}")
    except FileNotFoundError as e:
        embed = Embed(title="Error",
                      description=f"Failed to delete the file. It might have been already deleted or not found: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"Failed to delete the file: {str(e)}")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"An error occurred: {str(error)}")


@bot.command()
@commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
async def ama_info(ctx, role: Union[discord.Role, int, str], member: discord.Member):
    try:
        # 입력값이 롤 객체인 경우
        if isinstance(role, discord.Role):
            role_found = role
        # 입력값이 역할 ID인 경우
        elif isinstance(role, int):
            role_found = discord.utils.get(ctx.guild.roles, id=role)
        # 입력값이 역할 이름인 경우
        else:
            role_found = discord.utils.get(ctx.guild.roles, name=role)

        if role_found is None:
            embed = Embed(title="Error",
                          description=f"❌ Role not found for name, ID, or mention `{role}`. Please enter a valid role name, ID, or mention.\n\n"
                                      f"❌ `{role}` 이름, ID 또는 멘션의 역할을 찾을 수 없습니다. 올바른 역할 이름, ID 또는 멘션을 입력해주세요.",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            return

        role_name = role_found.name

        # 데이터베이스에서 사용자 정보 조회
        user_summary = await get_user_summary_from_db(role_name, member.id)
        if user_summary:
            # 시간을 분과 초로 변환
            total_seconds = user_summary['time_spent']
            minutes, seconds = divmod(total_seconds, 60)
            if minutes > 0:
                time_spent_str = f"`{minutes}` minutes `{seconds}` seconds"
            else:
                time_spent_str = f"`{seconds}` seconds"

            embed = Embed(title=f"{role_name} Summary for {member.display_name}",
                          description=f"- Total Messages: `{user_summary['total_messages']}`\n"
                                      f"- Valid Messages: `{user_summary['valid_messages']}`\n"
                                      f"- AMA VC Joins: `{user_summary['total_joins']}`\n"
                                      f"- AMA VC Leaves: `{user_summary['total_leaves']}`\n"
                                      f"- Time Spent: {time_spent_str}",
                          color=0x37e37b)
        else:
            embed = Embed(title="No Data Found",
                          description=f"No summary data found for {member.display_name} in {role_name}.",
                          color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
    except Exception as e:
        embed = Embed(title="Error",
                      description=f"An error occurred: {str(e)}",
                      color=0xff0000)
        await ctx.reply(embed=embed, mention_author=True)
        logger.error(f"An error occurred: {str(e)}")


async def get_user_summary_from_db(role_name, user_id):
    connection = db.get_connection()
    cursor = connection.cursor()
    user_summary = None
    try:
        # 사용자 요약 정보 조회
        cursor.execute("""
            SELECT * FROM ama_users_summary
            WHERE role_name = %s AND user_id = %s
            """, (role_name, str(user_id)))
        result = cursor.fetchone()
        if result:
            user_summary = {
                'total_messages': result['total_messages'],
                'valid_messages': result['valid_messages'],
                'total_joins': result['total_joins'],
                'total_leaves': result['total_leaves'],
                'time_spent': result['time_spent']
            }
    except Exception as e:
        logger.error(f'DB error: {e}')
    finally:
        cursor.close()
        connection.close()
    return user_summary


@bot.command()
async def bulk_assign_role(ctx, role: discord.Role):
    user_ids = [
        1000693846205800469,
        1012082539566989342,
        1013591786985365575,
        1015737051469062245,
        1018859325227278416,
        1021180252279554121,
        1022958295482388481,
        1032222097646288906,
        1034103137449029652,
        1034489951309545602,
        1035899540429086751,
        1039500529816047688,
        1043636207516667965,
        1045113473073430598,
        1056491548721819688,
        1061562005187727473,
        1065936887111503903,
        1065954166754787398,
        1066080002845708440,
        1068111322811727943,
        1068922997651542046,
        1070037529799168122,
        1078943468983943189,
        1084152932762669187,
        1085315720365224026,
        1087766296390807552,
        1090764482990592010,
        1091460777715708094,
        1092849329716351138,
        1093822671189442570,
        1114320486340513822,
        1114984309758099579,
        1120863717320568902,
        1133718478499627129,
        1142562643505336380,
        1143459001368064081,
        1146122212437393458,
        1149087935216504973,
        1152671542975664200,
        1154434984220827739,
        1155825545007857694,
        1157204746432696354,
        1166684499334148168,
        190868525873758209,
        194828121499893771,
        216648801899905024,
        228186428205432833,
        236438774861660160,
        244381062753419264,
        285167032885051392,
        307546180169105409,
        326352735018680321,
        332183935364759562,
        336544647272857600,
        341686158180483074,
        342294904245846016,
        346852297697132544,
        351236056483364864,
        363285769756082178,
        364256788918304768,
        365899136198901771,
        392304188274769941,
        394784215981359115,
        395814118461800449,
        404928667425308682,
        410467315608584192,
        426382192634232833,
        428964034159575040,
        433564409051217920,
        452298540509560843,
        456790953563258882,
        464797945573933066,
        466568490669834255,
        469481016093048854,
        482287486018781225,
        499958513217568768,
        502855264051920897,
        507341260650971137,
        507561287748943882,
        516820278870016035,
        516825481257943041,
        518723907813900305,
        518798517003878400,
        521301715199328257,
        531781653954035715,
        534374899117064204,
        545847242632855573,
        546708520343699466,
        605703134098227231,
        609934212014932042,
        627498599458144257,
        628074315274911744,
        638479745906114572,
        693416975220604949,
        700083885353992794,
        705055653437112410,
        710488978020761612,
        713701674291822652,
        717266594673328198,
        717685615747137576,
        730074607377449013,
        748186107539226664,
        751432663147085825,
        761610131154403349,
        761763558404128779,
        764739699834093580,
        764842596421074954,
        770170022223020054,
        802951857898913824,
        804621142543171614,
        806235134516002897,
        809278064018194442,
        812201142041837600,
        817751298119827499,
        827555957617590303,
        831157309367517284,
        831797383468810241,
        831856737606565928,
        835123641334628392,
        836658587534229504,
        837972644409114634,
        845309743518056498,
        845706794080403496,
        847568725535621140,
        849329641927737384,
        850340759303487498,
        850998633649274930,
        855422311548977172,
        857200472120229889,
        858153167903653908,
        859215503481503784,
        865217125161500704,
        867852104084357142,
        869547323385065523,
        878530522563887104,
        881548267144482866,
        883764527332737064,
        885034104947605545,
        885498997396107355,
        886189458486083596,
        886373719289778226,
        888327065521258508,
        889190633036714084,
        889535587793662043,
        890160708891856956,
        890223882039066644,
        891672724043350096,
        891695358881718313,
        892249831861534720,
        893131966642270298,
        894080673407717416,
        896281310925041694,
        896451419350134824,
        900580770362576966,
        902003287157518367,
        902608853999427604,
        903417556990296085,
        905728632914317352,
        907648295793487872,
        908380522403750008,
        909080516832141312,
        913223759400415272,
        913462969537531944,
        913694863847993354,
        914878793854885908,
        914940680713936927,
        915139373098500117,
        917643567776821278,
        917983330719371344,
        918264789694812160,
        918277794407018506,
        921156882968760351,
        921711266165313546,
        923569969411792957,
        924627466134372413,
        925486418883665960,
        926163499435040769,
        926351929091719189,
        926741066156236850,
        927229076081610762,
        927380365612572732,
        928677684022759444,
        929409454838005770,
        930730752058994719,
        931076583396102184,
        931230981086670849,
        931857748486942810,
        934146025311051817,
        936371257413345300,
        937767058337329192,
        938802213009117214,
        939467740400472098,
        940788149691486248,
        941010057406079046,
        942027723130437633,
        942319099470553120,
        942871479996010576,
        944555712695115786,
        945495792523829310,
        947978829819957358,
        948285725915369482,
        948529986858520617,
        949271565810425896,
        950735073378988082,
        950763933038440479,
        951420547584110613,
        952224070546624582,
        952249074705371177,
        952263511348760647,
        952277050041978911,
        952279976344948846,
        952399346303893524,
        952500596395614218,
        952503065917935676,
        952503805256278056,
        952532222508933130,
        952532347142680599,
        952534057269469245,
        952562781385805864,
        952576465726226432,
        952586395191500852,
        952597610093486090,
        952598691624124496,
        952604917472845845,
        952612912713854996,
        952626002331312158,
        952679345762213978,
        952681914991513690,
        952746156495085608,
        952781661639164004,
        952792958694993941,
        952815496036765737,
        952821785433358386,
        953247410363183145,
        953600347925020682,
        954682271540076554,
        954866675814121583,
        956211462626480199,
        956237355965100082,
        960573814851375184,
        961044323170918471,
        961547604553007104,
        963115711553765488,
        964907903515492475,
        965058320891248650,
        965262102820429834,
        965597801222381638,
        965866307436286015,
        966005580827353278,
        966749868708220978,
        971090377354399774,
        972240396740599888,
        974019048490815620,
        979889653916262420,
        981305139249954897,
        985223338383273994,
        988439692682862622,
        992377835815706624,
        993920014480580749,
        994508399641378897,
        995954911793647687,
        996166536454742067,
        997417987084664864,
        998121253112127578,
        999606976180924427
    ]

    for user_id in user_ids:
        member = ctx.guild.get_member(user_id)
        if member is not None:
            try:
                await member.add_roles(role)
                await ctx.send(f"Role {role.name} has been assigned to {member.display_name}.")
            except discord.Forbidden:
                await ctx.send(f"Failed to assign role to {member.display_name}. Check the bot's permissions.")
            except discord.HTTPException as e:
                await ctx.send(f"HTTP exception while assigning role to {member.display_name}: {str(e)}")
        else:
            await ctx.send(f"Member with ID {user_id} not found.")


@bot.command()
async def bulk_remove_role(ctx, role: discord.Role):
    user_ids = [
        332183935364759562,
        770170022223020054,
        952821785433358386,
        952399346303893524,
        865217125161500704,
        893131966642270298,
        1039500529816047688,
        952263511348760647,
        952597610093486090,
        952500596395614218,
        952576465726226432,
        952746156495085608,
        428964034159575040,
        952532222508933130,
        952612912713854996,
        952532347142680599,
        952562781385805864,
        952792958694993941,
        952781661639164004,
        952604917472845845,
        952681914991513690,
        507561287748943882,
        902608853999427604,
        456790953563258882,
        952534057269469245,
        952249074705371177,
        952279976344948846,
        952626002331312158,
        952679345762213978,
        952224070546624582,
        952277050041978911,
        952586395191500852,
        952503805256278056,
        952815496036765737,
        952503065917935676,
        952598691624124496,
        1012082539566989342,
        888327065521258508,
        751432663147085825,
        902003287157518367,
        948529986858520617,
        998121253112127578,
        831157309367517284,
        931857748486942810,
        927229076081610762,
        954682271540076554,
        1154434984220827739,
        857200472120229889,
        638479745906114572,
        518723907813900305,
        926741066156236850,
        950763933038440479,
        717266594673328198,
        849329641927737384,
        924627466134372413,
        464797945573933066,
        827555957617590303,
        341686158180483074
    ]

    for user_id in user_ids:
        member = ctx.guild.get_member(user_id)
        if member is not None:
            try:
                await member.remove_roles(role)
                await ctx.send(f"Role {role.name} has been removed from {member.display_name}.")
            except discord.Forbidden:
                await ctx.send(f"Failed to remove role from {member.display_name}. Check the bot's permissions.")
            except discord.HTTPException as e:
                await ctx.send(f"HTTP exception while removing role from {member.display_name}: {str(e)}")
        else:
            await ctx.send(f"Member with ID {user_id} not found.")


bot.run(bot_token)
