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
                      description=f"✅ AMA session has ended!\n"
                                  f"Run the `!bulk_assign_role <Role>` command to assign a role.\n\n"
                                  f"✅ AMA 세션이 종료되었습니다!\n"
                                  f"`!bulk_assign_role <Role>` 명령어를 실행하여 롤을 부여해주세요.",
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
                                  f"Soon an Excel file will be created.\n"
                                  f"Please wait a moment.\n\n"
                                  f"✅ `{now}` 스냅샷이 생성되었습니다.\n"
                                  f"곧 엑셀파일이 생성됩니다.\n"
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
        user_summary, all_snapshot = await get_user_summary_from_db(role_name, member.id)
        all_snapshot_description = "```\n"
        all_snapshot_description += "{:<6s}{:<7s}{:<6s}{:<6s}{:<6s}{:<7s}{:<10s}\n".format(
            "snap", "status", "total", "valid", "joins", "leaves", "time_spent")
        all_snapshot_description += "-" * 48 + "\n"
        index = 1
        for row in all_snapshot:
            if row["snap_time"] == "final_snapshot":
                snap = "final"
            else:
                snap = index
            total_seconds = int(row['time_spent'])
            minutes, seconds = divmod(total_seconds, 60)
            if minutes > 0:
                time_spent_str = f"`{minutes}` m `{seconds}` s"
            else:
                time_spent_str = f"`{seconds}` s"
            all_snapshot_description += "{:<6s}{:<7s}{:<6s}{:<6s}{:<6s}{:<7s}{:<10s}\n".format(
                f"{snap}", row["ama_status"], row["total_msg"], row["valid_msg"],
                row["total_joins"], row["total_leaves"], time_spent_str)
            index += 1
        all_snapshot_description += "```"
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
                                      f"- Time Spent: {time_spent_str}\n\n"
                                      f"- All Snapshot\n"
                                      f"{all_snapshot_description}",
                          color=0x37e37b)
        else:
            embed = Embed(title="No Data Found",
                          description=f"No summary data found for {member.display_name} in {role_name}.\n\n"
                                      f"- All Snapshot\n"
                                      f"{all_snapshot_description}",
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
    all_snapshot = []
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

        cursor.execute("""
            with all_snapshot as (
                select role_id, role_name, timestamp
                from ama_users_summary_snapshot
                where role_name = %s
                group by role_id, role_name, timestamp
                union all
                select role_id, role_name, 'final_snapshot'
                from ama_users_summary
                where role_name = %s
                group by role_id, role_name
            )
            select main.role_id,
                   main.role_name,
                   main.timestamp,
                   IF(user_snapshot.user_id is null, 'OUT', 'IN') ama_status,
                   user_snapshot.total_messages,
                   user_snapshot.valid_messages,
                   user_snapshot.total_joins,
                   user_snapshot.total_leaves,
                   user_snapshot.time_spent
            from all_snapshot as main
            left outer join (
                select 
                    user_id,
                    total_messages,
                    valid_messages,
                    total_joins,
                    total_leaves,
                    time_spent,
                    timestamp
                from ama_users_summary_snapshot
                where role_name = %s
                and user_id = %s
                union all
                select 
                    user_id,
                    total_messages,
                    valid_messages,
                    total_joins,
                    total_leaves,
                    time_spent,
                    'final_snapshot'
                from ama_users_summary
                where role_name = %s
                and user_id = %s
            ) as user_snapshot on main.timestamp = user_snapshot.timestamp
            order by main.timestamp
        """, (role_name, role_name, role_name, str(user_id), role_name, str(user_id)))
        result = cursor.fetchall()
        for row in result:
            all_snapshot.append({
                'snap_time': str(row['timestamp']),
                'ama_status': str(row['ama_status']),
                'total_msg': str(row['total_messages']),
                'valid_msg': str(row['valid_messages']),
                'total_joins': str(row['total_joins']),
                'total_leaves': str(row['total_leaves']),
                'time_spent': str(row['time_spent'])
            })
    except Exception as e:
        logger.error(f'get_user_summary_from_db DB error: {e}')
    finally:
        cursor.close()
        connection.close()
    return user_summary, all_snapshot


@bot.command()
async def bulk_assign_role(ctx, role: Union[discord.Role, int, str]):
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

    connection = db.get_connection()
    cursor = connection.cursor()
    user_ids = []
    try:
        cursor.execute("""
            select user_id
            from ama_users_summary
            where role_name = %s
            and valid_messages > 0
            """, role_found.name)
        result = cursor.fetchall()
        for user_id in result:
            user_ids.append(user_id['user_id'])
        if len(user_ids) > 0:
            for user_id in user_ids:
                member = ctx.guild.get_member(int(user_id))
                if member is not None:
                    try:
                        await member.add_roles(role_found)
                        await ctx.send(f"Role `{role_found.name}` has been assigned to `{member.name}`.")
                    except discord.Forbidden:
                        await ctx.send(f"Failed to assign role to `{member.name}`. Check the bot's permissions.")
                    except discord.HTTPException as e:
                        await ctx.send(f"HTTP exception while assigning role to `{member.name}`: {str(e)}")
                else:
                    await ctx.send(f"Member with ID `{user_id}` not found.")
            embed = Embed(title=f"{role_found.name} assigned",
                          description=f"Role assignment for Role `{role_found.name}` completed!",
                          color=0x37e37b)
            await ctx.reply(embed=embed)
        else:
            embed = Embed(title="Error",
                          description=f"❌ The target to assign {role} is not queried.\n\n"
                                      f"❌ {role}을 부여할 대상이 조회되지 않습니다.",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            return
    except Exception as e:
        logger.error(f'DB error: {e}')
    finally:
        cursor.close()
        connection.close()


@bot.command()
async def bulk_remove_role(ctx, role: Union[discord.Role, int, str]):
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

    connection = db.get_connection()
    cursor = connection.cursor()
    user_ids = []
    try:
        cursor.execute("""
            select user_id
            from ama_users_summary
            where role_name = %s
            and valid_messages = 0
            """, role_found.name)
        result = cursor.fetchall()
        if result:
            user_ids.append(result['user_id'])
        if len(user_ids) > 0:
            for user_id in user_ids:
                member = ctx.guild.get_member(int(user_id))
                if member is not None:
                    try:
                        await member.remove_roles(role_found)
                        await ctx.send(f"Role `{role_found.name}` has been removed from `{member.name}`.")
                    except discord.Forbidden:
                        await ctx.send(f"Failed to remove role from `{member.name}`. Check the bot's permissions.")
                    except discord.HTTPException as e:
                        await ctx.send(f"HTTP exception while removing role from `{member.name}`: {str(e)}")
                else:
                    await ctx.send(f"Member with ID `{user_id}` not found.")
            embed = Embed(title=f"{role_found.name} removed",
                          description=f"Role remove for Role `{role_found.name}` completed!",
                          color=0x37e37b)
            await ctx.reply(embed=embed)
        else:
            embed = Embed(title="Error",
                          description=f"❌ The target to remove {role} is not queried.\n\n"
                                      f"❌ {role}을 제거할 대상이 조회되지 않습니다.",
                          color=0xff0000)
            await ctx.reply(embed=embed, mention_author=True)
            return
    except Exception as e:
        logger.error(f'DB error: {e}')
    finally:
        cursor.close()
        connection.close()


bot.run(bot_token)
