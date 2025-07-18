import discord
import os
import io
import logging
import asyncio
import pymysql
import chat_exporter
import pytz
from discord import *
from discord.ui import View, Button
from discord.ext import commands, tasks
from discord.ext.pages import Paginator
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv
from contextlib import contextmanager

load_dotenv()

bot_token = os.getenv("SEARCHFI_TICKET_BOT_TOKEN")
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
guild_id = int(os.getenv('SELF_GUILD_ID'))
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")
category_id1 = int(os.getenv('TICKET_CATEGORY_ID1'))
category_id2 = int(os.getenv('TICKET_CATEGORY_ID2'))
team_role1 = int(os.getenv('TICKET_TEAM_ROLE_ID1'))
team_role2 = int(os.getenv('TICKET_TEAM_ROLE_ID2'))
ticket_channel_id = int(os.getenv('TICKET_CHANNEL_ID'))
log_channel_id = int(os.getenv('TICKET_LOG_CHANNEL_ID'))
timezone = "Asia/Seoul"
bot_log_folder = os.getenv("BOT_LOG_FOLDER")

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(filename=f"{bot_log_folder}/ticket_bot.log", mode='a'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

bot = commands.Bot(command_prefix=f"{command_flag}", intents=discord.Intents.all())


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
    
    @contextmanager
    def get_cursor(self):
        """Context manager for database cursor"""
        connection = self.get_connection()
        cursor = connection.cursor()
        try:
            yield cursor
            connection.commit()
        except Exception as e:
            connection.rollback()
            raise e
        finally:
            cursor.close()
            connection.close()


db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)


class TicketSystem(commands.Cog):
    def __init__(self, bot:Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Bot Loaded | ticket_system.py ✅')
        view = TicketView()
        view.add_item(Button(label="Collab",
                             emoji="🤝",
                             style=discord.ButtonStyle.link,
                             url="https://discord.gg/cqW8RsEk4s"))
        self.bot.add_view(view)
        self.bot.add_view(CloseButton())
        self.bot.add_view(TicketOptions())


async def make_button(category_id: int, interaction: Interaction):
    category = interaction.guild.get_channel(category_id)

    if interaction.channel.id == ticket_channel_id:
        guild = interaction.guild
        user_id = interaction.user.id
        user_name = interaction.user.name
        
        try:
            with db.get_cursor() as cursor:
                cursor.execute(
                    """
                        SELECT user_id
                        FROM tickets
                        WHERE user_id = %s
                        and category_id = %s
                        and ticket_status = 'OPEN'
                    """,
                    (user_id, category_id)
                )
                existing_ticket = cursor.fetchone()
                
                if existing_ticket is None:
                    cursor.execute(
                        """
                            INSERT INTO tickets (category_id, category_name, user_id, user_name)
                            VALUES (%s, %s, %s, %s)
                        """,
                        (category_id, category.name, user_id, user_name)
                    )
                    
                    cursor.execute(
                        """
                            SELECT id
                            FROM tickets
                            WHERE category_id = %s
                            and user_id = %s
                            and ticket_status = 'OPEN'
                        """,
                        (category_id, user_id))
                    ticket_number = cursor.fetchone()['id']
                    
                    ticket_channel = await guild.create_text_channel(f"{user_name}-ticket",
                                                                     category=category,
                                                                     topic=f"{interaction.user.id}-{ticket_number}")
                    
                    # 권한 설정을 함수로 분리
                    await set_ticket_permissions(ticket_channel, guild, interaction.user)

                    if category_id == category_id1:
                        title = "☎️  Support Ticket"
                        description = "This is a ticket for suggestions and reports.\n\n" \
                                      "If you open the wrong ticket, please close it.\n\n"\
                                      "Based on the example below, please write down the content that will help the community.\n"\
                                      "(Anything is possible, even if it is not an example.)\n\n"\
                                      "ㆍInconvenience\n"\
                                      "ㆍProposal items\n"\
                                      "ㆍEvent proposal\n"\
                                      "ㆍReporting scams"
                    else:
                        title = "🎉  Giveaway Winner Ticket"
                        description = "Please leave a proof photo (screenshot) and wallet address after opening the ticket.\n\n" \
                                      "ㆍDiscord : Discord G/A screenshot\n" \
                                      "ㆍTwitter : Screenshot of winning, DM history, your profile (to show profile correction)" \

                    embed = Embed(title=title,
                                  description=description,
                                  color=discord.colour.Color.blue())
                    await ticket_channel.send(content=f"{interaction.user.mention}",
                                              embed=embed,
                                              view=CloseButton())

                    embed = Embed(description=f'📬 Ticket was Created! Look here --> {ticket_channel.mention}',
                                  color=discord.colour.Color.green())
                    await interaction.followup.send(embed=embed, ephemeral=True)
                else:
                    embed = Embed(title="You already have an open ticket", color=0xff0000)
                    await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as error:
            logger.error(f"Error in make_button: {str(error)}")
            embed = Embed(title="Error", description="Failed to create ticket. Please try again.", color=0xff0000)
            await interaction.followup.send(embed=embed, ephemeral=True)


async def set_ticket_permissions(channel, guild, user):
    """Set permissions for ticket channel"""
    team_role1_obj = guild.get_role(team_role1)
    team_role2_obj = guild.get_role(team_role2)
    
    # Team roles permissions
    for role in [team_role1_obj, team_role2_obj]:
        if role:
            await channel.set_permissions(role,
                                         send_messages=True,
                                         read_messages=True,
                                         add_reactions=False,
                                         embed_links=True,
                                         attach_files=True,
                                         read_message_history=True,
                                         external_emojis=True)
    
    # User permissions
    await channel.set_permissions(user,
                                 send_messages=True,
                                 read_messages=True,
                                 add_reactions=False,
                                 embed_links=True,
                                 attach_files=True,
                                 read_message_history=True,
                                 external_emojis=True,
                                 use_slash_commands=False)
    
    # Default role permissions (deny all)
    await channel.set_permissions(guild.default_role,
                                 send_messages=False,
                                 read_messages=False,
                                 view_channel=False)


class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support", emoji="☎️", style=discord.ButtonStyle.blurple, custom_id="support")
    async def support(self, _, interaction: Interaction):
        try:
            await interaction.response.defer()
            await make_button(category_id1, interaction)
        except Exception as error:
            logger.error(f"An error occurred: {str(error)}")

    @discord.ui.button(label="Giveaway Winner", emoji="🎉", style=discord.ButtonStyle.blurple, custom_id="giveaway_winner")
    async def giveaway_winner(self, _, interaction: Interaction):
        try:
            await interaction.response.defer()
            await make_button(category_id2, interaction)
        except Exception as error:
            logger.error(f"An error occurred: {str(error)}")


class CloseButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket 🎫", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, button: Button, interaction: Interaction):
        try:
            guild = interaction.guild
            ticket_topic = interaction.channel.topic
            
            with db.get_cursor() as cursor:
                cursor.execute(
                    """
                        SELECT id, user_id
                        FROM tickets 
                        WHERE concat(user_id,'-',id) = %s
                        and ticket_status = 'OPEN'
                    """,
                    (ticket_topic,)
                )
                ticket = cursor.fetchone()
                
                if not ticket:
                    embed = Embed(title="Error", description="Ticket not found or already closed.", color=0xff0000)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                ticket_id = ticket.get("id")
                ticket_user_id = ticket.get("user_id")
                ticket_creator = guild.get_member(int(ticket_user_id))

                cursor.execute(
                    """
                        UPDATE tickets SET ticket_status = 'CLOSE'
                        WHERE id = %s
                    """,
                    (ticket_id,)
                )

            embed = Embed(title="Ticket Closed 🎫",
                          description=f"The ticket has been closed by {ticket_creator}",
                          color=discord.colour.Color.green())
            
            # 사용자 권한 제거
            await interaction.channel.set_permissions(ticket_creator,
                                                      send_messages=False,
                                                      read_messages=False,
                                                      add_reactions=False,
                                                      embed_links=False,
                                                      attach_files=False,
                                                      read_message_history=False,
                                                      external_emojis=False)
            
            await interaction.channel.edit(name=f"ticket-closed-{ticket_creator.name}-ticket")
            await interaction.response.send_message(embed=embed,
                                                    view=TicketOptions())
            button.disabled = True
            await interaction.message.edit(view=self)
        except Exception as error:
            logger.error(f"Error in close button: {str(error)}")
            embed = Embed(title="Error", description="Failed to close ticket. Please try again.", color=0xff0000)
            await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketOptions(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Delete Ticket 🎫", style=discord.ButtonStyle.red, custom_id="delete")
    async def delete_button(self, button: Button, interaction: Interaction):
        try:
            guild = interaction.guild
            log_channel = interaction.guild.get_channel(log_channel_id)
            ticket_topic = interaction.channel.topic

            # 1단계: 티켓 정보 조회
            with db.get_cursor() as cursor:
                cursor.execute(
                    """
                        SELECT id, user_id, category_name
                        FROM tickets 
                        WHERE concat(user_id, '-', id) = %s
                        and ticket_status = 'CLOSE'
                    """,
                    (ticket_topic,)
                )
                ticket = cursor.fetchone()
                
                if not ticket:
                    embed = Embed(title="Error", description="Ticket not found or not closed.", color=0xff0000)
                    await interaction.response.send_message(embed=embed, ephemeral=True)
                    return
                
                ticket_id = ticket.get("id")
                ticket_user_id = ticket.get("user_id")
                ticket_category_name = ticket.get("category_name")
                ticket_creator = guild.get_member(int(ticket_user_id))

            # 2단계: 트랜스크립트 생성
            military_time: bool = True
            transcript = await chat_exporter.export(
                interaction.channel,
                limit=500,
                tz_info=timezone,
                military_time=military_time,
                bot=bot,
            )
            if transcript is None:
                embed = Embed(title="Error", description="Failed to create transcript.", color=0xff0000)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            else:
                lines = transcript.split('\n')

                new_transcript = ""
                for line in lines:
                    if "https://media.discordapp.net/attachments" in line:
                        new_line = line.replace("https://media.discordapp.net/attachments", "https://cdn.discordapp.com/attachments")
                        new_transcript += new_line
                    else:
                        new_transcript += line
                transcript = new_transcript

            # 3단계: DB 상태 업데이트 (가장 중요한 부분)
            update_success = False
            try:
                with db.get_cursor() as cursor:
                    cursor.execute(
                        """
                            UPDATE tickets SET ticket_status = 'DELETE', ticket_description = %s
                            WHERE concat(user_id, '-', id) = %s
                            and ticket_status = 'CLOSE' 
                        """,
                        (transcript, ticket_topic,)
                    )
                    # 업데이트된 행 수 확인
                    if cursor.rowcount > 0:
                        update_success = True
                        logger.info(f"Successfully updated ticket {ticket_id} status to DELETE")
                    else:
                        logger.error(f"No rows updated for ticket {ticket_id}")
            except Exception as db_error:
                logger.error(f"Database update failed for ticket {ticket_id}: {str(db_error)}")
                embed = Embed(title="Database Error", description="Failed to update ticket status in database.", color=0xff0000)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            if not update_success:
                embed = Embed(title="Error", description="Failed to update ticket status. Please try again.", color=0xff0000)
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            # 4단계: 파일 생성 및 메시지 전송
            transcript_file = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{interaction.channel.name}.html")
            transcript_file2 = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{interaction.channel.name}.html")

            embed = Embed(description='Ticket is deleting in 5 seconds.', color=0xff0000)
            transcript_info = Embed(title=f"Ticket Deleting | {interaction.channel.name}",
                                    description=f"- **Ticket ID:** {ticket_id}\n"
                                                f"- **Ticket from:** {ticket_creator.mention}\n"
                                                f"- **Ticket Name:** {interaction.channel.name} \n"
                                                f"- **Ticket Type:** {ticket_category_name}\n"
                                                f"- **Closed from:** {interaction.user.mention}",
                                    color=discord.colour.Color.blue())

            await interaction.response.send_message(embed=embed)

            try:
                await ticket_creator.send(embed=transcript_info,
                                          file=transcript_file)
            except Exception as e:
                logger.warning(f"Could not send transcript to user {ticket_creator.id}: {e}")
                transcript_info.add_field(name="Error",
                                          value="Couldn't send the Transcript to the User because he has his DMs disabled!",
                                          inline=True)
            
            await log_channel.send(embed=transcript_info,
                                   file=transcript_file2)
            
            # 5단계: 채널 삭제 (DB 업데이트가 성공한 후에만)
            await asyncio.sleep(3)
            try:
                await interaction.channel.delete(reason="Ticket got Deleted!")
                logger.info(f"Successfully deleted channel for ticket {ticket_id}")
            except Exception as delete_error:
                logger.error(f"Failed to delete channel for ticket {ticket_id}: {str(delete_error)}")
                # 채널 삭제 실패 시에도 DB는 이미 업데이트되었으므로 성공으로 처리
                
        except Exception as error:
            logger.error(f"Error in delete button: {str(error)}")
            embed = Embed(title="Error", description="Failed to delete ticket. Please try again.", color=0xff0000)
            await interaction.response.send_message(embed=embed, ephemeral=True)


class TicketCommand(commands.Cog):

    def __init__(self, bot):
        self.embed = None
        self.channel = None
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Bot Loaded | ticket_commands.py ✅')

    @commands.slash_command(
        name="ticket",
        description="Create ticket support",
        guild_ids=[guild_id]
    )
    @commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
    async def ticket(self, ctx: ApplicationContext):
        try:
            self.channel = self.bot.get_channel(ticket_channel_id)
            description = "Of the two tickets, you can open a ticket that meets your request. Penalties may be imposed if you open a ticket of a different kind than the one requested.\n\n" \
                          "☎️ **Support**\n\n" \
                          "> This is a ticket for suggestions and reports.\n" \
                          "> ㆍCommunity inconvenience or suggestions for our community.\n" \
                          "> ㆍReporting scams impersonating our community (with relevant link and screenshot)\n\n" \
                          "🎉 **Giveaway Winner**\n\n" \
                          "> Please open the event winners only.\n" \
                          f"> Please check <#{ticket_channel_id}> before opening the ticket."
            embed = discord.Embed(title="Open a ticket",
                                  description=description,
                                  color=discord.colour.Color.blue())
            view = TicketView()
            view.add_item(Button(label="Collab",
                                 emoji="🤝",
                                 style=discord.ButtonStyle.link,
                                 url="https://discord.gg/cqW8RsEk4s"))
            await self.channel.send(embed=embed, view=view)
            await ctx.respond("Ticket Menu was send!", ephemeral=True)
        except Exception as error:
            logger.error(f"An error occurred: {str(error)}")

    @commands.slash_command(
        name="close-ticket",
        description="Close the Ticket",
        guild_ids=[guild_id]
    )
    @commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
    async def close(self, ctx: ApplicationContext):
        try:
            guild = ctx.guild
            ticket_topic = ctx.channel.topic
            
            with db.get_cursor() as cursor:
                cursor.execute(
                    """
                        SELECT id, user_id
                        FROM tickets 
                        WHERE concat(user_id,'-',id) = %s
                        and ticket_status = 'OPEN'
                    """,
                    (ticket_topic,)
                )
                ticket = cursor.fetchone()
                
                if not ticket:
                    embed = Embed(title="Error", description="Ticket not found or already closed.", color=0xff0000)
                    await ctx.response.send_message(embed=embed, ephemeral=True)
                    return
                
                ticket_id = ticket.get("id")
                ticket_user_id = ticket.get("user_id")
                ticket_creator = guild.get_member(int(ticket_user_id))

                cursor.execute(
                    """
                        UPDATE tickets SET ticket_status = 'CLOSE'
                        WHERE id = %s
                    """,
                    (ticket_id,)
                )

            embed = Embed(title="Ticket Closed 🎫",
                          description=f"The ticket has been closed by {ticket_creator}",
                          color=discord.colour.Color.green())
            await ctx.channel.set_permissions(ticket_creator,
                                                      send_messages=False,
                                                      read_messages=False,
                                                      add_reactions=False,
                                                      embed_links=False,
                                                      attach_files=False,
                                                      read_message_history=False,
                                                      external_emojis=False)
            await ctx.channel.edit(name=f"ticket-closed-{ticket_creator.name}-ticket")
            await ctx.response.send_message(embed=embed,
                                                    view=TicketOptions())
        except Exception as error:
            logger.error(f"Error in close command: {str(error)}")
            embed = Embed(title="Error", description="Failed to close ticket. Please try again.", color=0xff0000)
            await ctx.response.send_message(embed=embed, ephemeral=True)

    @commands.slash_command(
        name="delete-ticket",
        description="Delete the Ticket",
        guild_ids=[guild_id]
    )
    @commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
    async def delete_ticket(self, ctx: ApplicationContext):
        try:
            guild = ctx.guild
            log_channel = ctx.guild.get_channel(log_channel_id)
            ticket_topic = ctx.channel.topic

            # 1단계: 티켓 정보 조회
            with db.get_cursor() as cursor:
                cursor.execute(
                    """
                        SELECT id, user_id, category_name
                        FROM tickets 
                        WHERE concat(user_id, '-', id) = %s
                        and ticket_status = 'CLOSE'
                    """,
                    (ticket_topic,)
                )
                ticket = cursor.fetchone()
                
                if not ticket:
                    embed = Embed(title="Error", description="Ticket not found or not closed.", color=0xff0000)
                    await ctx.response.send_message(embed=embed, ephemeral=True)
                    return
                
                ticket_id = ticket.get("id")
                ticket_user_id = ticket.get("user_id")
                ticket_category_name = ticket.get("category_name")
                ticket_creator = guild.get_member(int(ticket_user_id))

            # 2단계: 트랜스크립트 생성
            military_time: bool = True
            transcript = await chat_exporter.export(
                ctx.channel,
                limit=500,
                tz_info=timezone,
                military_time=military_time,
                bot=bot,
            )
            if transcript is None:
                embed = Embed(title="Error", description="Failed to create transcript.", color=0xff0000)
                await ctx.response.send_message(embed=embed, ephemeral=True)
                return
            else:
                lines = transcript.split('\n')

                new_transcript = ""
                for line in lines:
                    if "https://media.discordapp.net/attachments" in line:
                        new_line = line.replace("https://media.discordapp.net/attachments", "https://cdn.discordapp.com/attachments")
                        new_transcript += new_line
                    else:
                        new_transcript += line
                transcript = new_transcript

            # 3단계: DB 상태 업데이트 (가장 중요한 부분)
            update_success = False
            try:
                with db.get_cursor() as cursor:
                    cursor.execute(
                        """
                            UPDATE tickets SET ticket_status = 'DELETE', ticket_description = %s
                            WHERE concat(user_id, '-', id) = %s
                            and ticket_status = 'CLOSE' 
                        """,
                        (transcript, ticket_topic,)
                    )
                    # 업데이트된 행 수 확인
                    if cursor.rowcount > 0:
                        update_success = True
                        logger.info(f"Successfully updated ticket {ticket_id} status to DELETE")
                    else:
                        logger.error(f"No rows updated for ticket {ticket_id}")
            except Exception as db_error:
                logger.error(f"Database update failed for ticket {ticket_id}: {str(db_error)}")
                embed = Embed(title="Database Error", description="Failed to update ticket status in database.", color=0xff0000)
                await ctx.response.send_message(embed=embed, ephemeral=True)
                return

            if not update_success:
                embed = Embed(title="Error", description="Failed to update ticket status. Please try again.", color=0xff0000)
                await ctx.response.send_message(embed=embed, ephemeral=True)
                return

            # 4단계: 파일 생성 및 메시지 전송
            transcript_file = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{ctx.channel.name}.html")
            transcript_file2 = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{ctx.channel.name}.html")

            embed = Embed(description='Ticket is deleting in 5 seconds.', color=0xff0000)
            transcript_info = Embed(title=f"Ticket Deleting | {ctx.channel.name}",
                                    description=f"- **Ticket ID:** {ticket_id}\n"
                                                f"- **Ticket from:** {ticket_creator.mention}\n"
                                                f"- **Ticket Name:** {ctx.channel.name} \n"
                                                f"- **Ticket Type:** {ticket_category_name}\n"
                                                f"- **Closed from:** {ctx.user.mention}",
                                    color=discord.colour.Color.blue())

            await ctx.response.send_message(embed=embed)

            try:
                await ticket_creator.send(embed=transcript_info,
                                          file=transcript_file)
            except Exception as e:
                logger.warning(f"Could not send transcript to user {ticket_creator.id}: {e}")
                transcript_info.add_field(name="Error",
                                          value="Couldn't send the Transcript to the User because he has his DMs disabled!",
                                          inline=True)
            
            await log_channel.send(embed=transcript_info,
                                   file=transcript_file2)
            
            # 5단계: 채널 삭제 (DB 업데이트가 성공한 후에만)
            await asyncio.sleep(3)
            try:
                await ctx.channel.delete(reason="Ticket got Deleted!")
                logger.info(f"Successfully deleted channel for ticket {ticket_id}")
            except Exception as delete_error:
                logger.error(f"Failed to delete channel for ticket {ticket_id}: {str(delete_error)}")
                # 채널 삭제 실패 시에도 DB는 이미 업데이트되었으므로 성공으로 처리
                
        except Exception as error:
            logger.error(f"Error in delete_ticket command: {str(error)}")
            embed = Embed(title="Error", description="Failed to delete ticket. Please try again.", color=0xff0000)
            await ctx.response.send_message(embed=embed, ephemeral=True)


    @commands.slash_command(
        name="ticket-search",
        description="Search ticket messages",
        guild_ids=[guild_id]
    )
    @commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
    async def ticket_search(self,
                            ctx: ApplicationContext,
                            search_user: Option(Member, "What users to search for", required=False),
                            search_message: Option(str, "What messages to search for", required=False)):
        try:
            if search_user is None and search_message is None:
                embed = Embed(title="Error",
                              description="You must enter either a user or a message that you want to search for.",
                              color=0xff0000)
                await ctx.respond(embed=embed, ephemeral=True)
                return

            # SQL injection 방지를 위해 조건을 안전하게 구성
            query = """
                SELECT id, user_id, user_name, category_name, ticket_created, ticket_status
                FROM tickets 
                WHERE 1=1
            """
            params = []
            
            if search_user:
                query += " AND user_id = %s"
                params.append(search_user.id)
            if search_message:
                query += " AND ticket_description LIKE %s"
                params.append(f"%{search_message}%")

            with db.get_cursor() as cursor:
                cursor.execute(query, params)
                tickets = cursor.fetchall()

            if not tickets:
                embed = Embed(title="No Results",
                              description="No tickets found matching your search criteria.",
                              color=0xff0000)
                await ctx.respond(embed=embed, ephemeral=True)
                return

            pages = []
            for ticket in tickets:
                ticket_id = ticket.get("id")
                ticket_user_id = ticket.get("user_id")
                ticket_user_name = ticket.get("user_name")
                ticket_category_name = ticket.get("category_name")
                ticket_created = ticket.get("ticket_created")
                ticket_created_utc = ticket_created.astimezone(pytz.utc)
                ticket_created_timestamp = int(ticket_created_utc.timestamp())
                ticket_status = ticket.get("ticket_status")

                embed = Embed(title=f"Searched Tickets\n> Search User: `{search_user}`\n> Search Message: `{search_message}`",
                              description=f"- **Ticket ID:** {ticket_id}\n"
                                          f"- **Ticket from:** {ticket_user_name}(ID: {ticket_user_id})\n"
                                          f"- **Ticket Type:** {ticket_category_name}\n"
                                          f"- **Ticket Created:** <t:{ticket_created_timestamp}:F> \n"
                                          f"- **Ticket Status:** {ticket_status}",
                              color=discord.colour.Color.blue())
                pages.append(embed)
            paginator = Paginator(pages=pages)
            await paginator.respond(ctx.interaction, ephemeral=False)
        except Exception as error:
            logger.error(f"Error in ticket_search: {str(error)}")
            embed = Embed(title="Error", description="Failed to search tickets. Please try again.", color=0xff0000)
            await ctx.respond(embed=embed, ephemeral=True)


@bot.event
async def on_ready():
    print(f'Bot Logged | {bot.user.name}')
    richpresence.start()


@tasks.loop(minutes=1)
async def richpresence():
    try:
        guild = bot.get_guild(guild_id)
        if not guild:
            logger.warning(f"Guild with ID {guild_id} not found")
            return
            
        category1 = discord.utils.get(guild.categories, id=int(category_id1))
        category2 = discord.utils.get(guild.categories, id=int(category_id2))
        
        # 카테고리가 None인 경우 처리
        category1_channels = len(category1.channels) if category1 else 0
        category2_channels = len(category2.channels) if category2 else 0
        
        total_channels = category1_channels + category2_channels
        
        await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,
                                                            name=f'Tickets | {total_channels}'))
    except Exception as error:
        logger.error(f"Error in richpresence task: {str(error)}")
        # 에러 발생 시 기본 상태로 설정
        try:
            await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,
                                                                name='Tickets | Error'))
        except:
            pass


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"An error occurred: {str(error)}")


bot.add_cog(TicketSystem(bot))
bot.add_cog(TicketCommand(bot))
bot.run(bot_token)
