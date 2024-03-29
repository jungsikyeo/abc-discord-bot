import discord
import os
import io
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


db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)
connection = db.get_connection()
cursor = connection.cursor()


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

    @commands.Cog.listener()
    async def on_bot_shutdown(self):
        cursor.close()
        connection.close()


async def make_button(category_id: int, interaction: Interaction):
    category = interaction.guild.get_channel(category_id)

    if interaction.channel.id == ticket_channel_id:
        guild = interaction.guild
        user_id = interaction.user.id
        user_name = interaction.user.name
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
            connection.commit()
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
            await ticket_channel.set_permissions(guild.get_role(team_role1),
                                                 send_messages=True,
                                                 read_messages=True,
                                                 add_reactions=False,
                                                 embed_links=True,
                                                 attach_files=True,
                                                 read_message_history=True,
                                                 external_emojis=True)
            await ticket_channel.set_permissions(guild.get_role(team_role2),
                                                 send_messages=True,
                                                 read_messages=True,
                                                 add_reactions=False,
                                                 embed_links=True,
                                                 attach_files=True,
                                                 read_message_history=True,
                                                 external_emojis=True)
            await ticket_channel.set_permissions(interaction.user,
                                                 send_messages=True,
                                                 read_messages=True,
                                                 add_reactions=False,
                                                 embed_links=True,
                                                 attach_files=True,
                                                 read_message_history=True,
                                                 external_emojis=True,
                                                 use_slash_commands=False)
            await ticket_channel.set_permissions(guild.default_role,
                                                 send_messages=False,
                                                 read_messages=False,
                                                 view_channel=False)

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
            embed = Embed(title=f"You already have a open Ticket", color=0xff0000)
            await interaction.followup.send(embed=embed, ephemeral=True)


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
            connection.commit()

            embed = Embed(title="Ticket Closed 🎫",
                          description=f"The ticket has been closed by {ticket_creator}",
                          color=discord.colour.Color.green())
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
            logger.error(f"An error occurred: {str(error)}")


class TicketOptions(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Delete Ticket 🎫", style=discord.ButtonStyle.red, custom_id="delete")
    async def delete_button(self, button: Button, interaction: Interaction):
        try:
            guild = interaction.guild
            log_channel = interaction.guild.get_channel(log_channel_id)
            ticket_topic = interaction.channel.topic

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
            ticket_id = ticket.get("id")
            ticket_user_id = ticket.get("user_id")
            ticket_category_name = ticket.get("category_name")
            ticket_creator = guild.get_member(int(ticket_user_id))

            # Creating the Transcript
            military_time: bool = True
            transcript = await chat_exporter.export(
                interaction.channel,
                limit=500,
                tz_info=timezone,
                military_time=military_time,
                bot=bot,
            )
            if transcript is None:
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

            cursor.execute(
                """
                    UPDATE tickets SET ticket_status = 'DELETE', ticket_description = %s
                    WHERE concat(user_id, '-', id) = %s
                    and ticket_status = 'CLOSE' 
                """,
                (transcript, ticket_topic,)
            )
            connection.commit()

            transcript_file = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{interaction.channel.name}.html")
            transcript_file2 = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{interaction.channel.name}.html")

            embed = Embed(description=f'Ticket is deliting in 5 seconds.', color=0xff0000)
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
            except:
                transcript_info.add_field(name="Error",
                                          value="Couldn't send the Transcript to the User because he has his DMs disabled!",
                                          inline=True)
            await log_channel.send(embed=transcript_info,
                                   file=transcript_file2)
            await asyncio.sleep(3)
            await interaction.channel.delete(reason="Ticket got Deleted!")
        except Exception as error:
            logger.error(f"An error occurred: {str(error)}")


class TicketCommand(commands.Cog):

    def __init__(self, bot):
        self.embed = None
        self.channel = None
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        print(f'Bot Loaded | ticket_commands.py ✅')

    @commands.Cog.listener()
    async def on_bot_shutdown(self):
        cursor.close()
        connection.close()

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
            connection.commit()

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
            logger.error(f"An error occurred: {str(error)}")

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
            ticket_id = ticket.get("id")
            ticket_user_id = ticket.get("user_id")
            ticket_category_name = ticket.get("category_name")
            ticket_creator = guild.get_member(int(ticket_user_id))

            # Creating the Transcript
            military_time: bool = True
            transcript = await chat_exporter.export(
                ctx.channel,
                limit=500,
                tz_info=timezone,
                military_time=military_time,
                bot=bot,
            )
            if transcript is None:
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

            cursor.execute(
                """
                    UPDATE tickets SET ticket_status = 'DELETE', ticket_description = %s
                    WHERE concat(user_id, '-', id) = %s
                    and ticket_status = 'CLOSE' 
                """,
                (transcript, ticket_topic,)
            )
            connection.commit()

            transcript_file = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{ctx.channel.name}.html")
            transcript_file2 = discord.File(
                io.BytesIO(transcript.encode()),
                filename=f"transcript-{ctx.channel.name}.html")

            embed = Embed(description=f'Ticket is deliting in 5 seconds.', color=0xff0000)
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
            except:
                transcript_info.add_field(name="Error",
                                          value="Couldn't send the Transcript to the User because he has his DMs disabled!",
                                          inline=True)
            await log_channel.send(embed=transcript_info,
                                   file=transcript_file2)
            await asyncio.sleep(3)
            await ctx.channel.delete(reason="Ticket got Deleted!")
        except Exception as error:
            logger.error(f"An error occurred: {str(error)}")


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
                              description=f"You must enter either a user or a message that you want to search for.",
                              color=0xff0000)
                await ctx.respond(embed=embed, ephemeral=True)
                return

            where = ""
            where_params = []
            if search_user:
                where += "and user_id = %s "
                where_params.append(search_user.id)
            if search_message:
                where += "and ticket_description like %s "
                where_params.append(f"%{search_message}%")

            cursor.execute(
                f"""
                    SELECT id, user_id, user_name, category_name, ticket_created, ticket_status
                    FROM tickets 
                    WHERE 1=1 
                        {where}
                """,
                where_params
            )
            tickets = cursor.fetchall()

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
            logger.error(f"An error occurred: {str(error)}")


@bot.event
async def on_ready():
    print(f'Bot Logged | {bot.user.name}')
    richpresence.start()


@tasks.loop(minutes=1)
async def richpresence():
    guild = bot.get_guild(guild_id)
    category1 = discord.utils.get(guild.categories, id=int(category_id1))
    category2 = discord.utils.get(guild.categories, id=int(category_id2))
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,
                                                        name=f'Tickets | {len(category1.channels) + len(category2.channels)}'))


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    else:
        logger.error(f"An error occurred: {str(error)}")


bot.add_cog(TicketSystem(bot))
bot.add_cog(TicketCommand(bot))
bot.run(bot_token)
