import discord
import os
import io
import pymysql
import chat_exporter
from discord import *
from discord.ui import View
from discord.ext import commands, tasks
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("SEARCHFI_BOT_TOKEN")
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
        self.bot.add_view(TicketView())
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
                                                 external_emojis=True)
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
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            embed = Embed(title=f"You already have a open Ticket", color=0xff0000)
            await interaction.response.send_message(embed=embed,
                                                    ephemeral=True)
    return


class TicketView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Support", emoji="☎️", style=discord.ButtonStyle.blurple, custom_id="support")
    async def support(self, _, interaction: Interaction):
        await make_button(category_id1, interaction)

    @discord.ui.button(label="Giveaway Winner", emoji="🎉", style=discord.ButtonStyle.blurple, custom_id="giveaway_winner")
    async def giveaway_winner(self, _, interaction: Interaction):
        await make_button(category_id2, interaction)


class CloseButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket 🎫", style=discord.ButtonStyle.danger, custom_id="close")
    async def close(self, button: Button, interaction: Interaction):
        guild = interaction.guild
        ticket_topic = interaction.channel.topic
        cursor.execute(
            """
                SELECT id, user_id
                FROM tickets 
                WHERE concat(user_id,'-',id) = %s
            """,
            (ticket_topic,)
        )
        ticket = cursor.fetchone()
        ticket_user_id = ticket.get("user_id")
        ticket_creator = guild.get_member(int(ticket_user_id))

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


class TicketOptions(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Delete Ticket 🎫", style=discord.ButtonStyle.red, custom_id="delete")
    async def delete_button(self, button: Button, interaction: Interaction):
        guild = interaction.guild
        log_channel = interaction.guild.get_channel(log_channel_id)
        ticket_topic = interaction.channel.topic

        cursor.execute(
            """
                SELECT id, user_id, category_name
                FROM tickets 
                WHERE concat(user_id, '-', id) = %s
            """,
            (ticket_topic,)
        )
        ticket = cursor.fetchone()
        ticket_user_id = ticket.get("user_id")
        ticket_category_name = ticket.get("category_name")
        ticket_creator = guild.get_member(int(ticket_user_id))

        cursor.execute(
            """
                DELETE FROM tickets 
                WHERE concat(user_id, '-', id) = %s
            """,
            (ticket_topic,)
        )
        connection.commit()

        # Creating the Transcript
        military_time: bool = True
        transcript = await chat_exporter.export(
            interaction.channel,
            limit=200,
            tz_info=timezone,
            military_time=military_time,
            bot=bot,
        )
        if transcript is None:
            return

        transcript_file = discord.File(
            io.BytesIO(transcript.encode()),
            filename=f"transcript-{interaction.channel.name}.html")
        transcript_file2 = discord.File(
            io.BytesIO(transcript.encode()),
            filename=f"transcript-{interaction.channel.name}.html")

        embed = Embed(description=f'Ticket is deliting in 5 seconds.', color=0xff0000)
        transcript_info = Embed(title=f"Ticket Deleting | {interaction.channel.name}",
                                description=f"- **Ticket from:** {ticket_creator.mention}\n"
                                            f"- **Ticket Name:** {interaction.channel.name} \n"
                                            f"- **Ticket Type:** {ticket_category_name}\n"
                                            f"- **Closed from:** {interaction.user.mention}",
                                color=discord.colour.Color.blue())

        await interaction.response.send_message(embed=embed)

        try:
            await ticket_creator.send(embed=transcript_info, file=transcript_file)
        except:
            transcript_info.add_field(name="Error",
                                      value="Couldn't send the Transcript to the User because he has his DMs disabled!",
                                      inline=True)
        await log_channel.send(embed=transcript_info, file=transcript_file2)
        await asyncio.sleep(3)
        await interaction.channel.delete(reason="Ticket got Deleted!")


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
        await self.channel.send(embed=embed, view=TicketView())
        await ctx.respond("Ticket Menu was send!", ephemeral=True)

    @commands.slash_command(
        name="add",
        description="Add a Member to the Ticket",
        guild_ids=[guild_id]
    )
    @commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
    async def add(self, ctx: ApplicationContext, member: Option(Member,
                                            description="Which Member you want to add to the Ticket",
                                            required=True)):
        if "-ticket" in ctx.channel.name or "ticket-closed-" in ctx.channel.name:
            await ctx.channel.set_permissions(member,
                                              send_messages=True,
                                              read_messages=True,
                                              add_reactions=False,
                                              embed_links=True,
                                              attach_files=True,
                                              read_message_history=True,
                                              external_emojis=True)
            self.embed = Embed(
                description=f"Added {member.mention} to this Ticket <#{ctx.channel.id}>! \n "
                            f"Use /remove to remove a User.",
                color=discord.colour.Color.green())
            await ctx.respond(embed=self.embed, ephemeral=True)
        else:
            self.embed = Embed(description=f'You can only use this command in a Ticket!',
                               color=discord.colour.Color.red())
            await ctx.respond(embed=self.embed, ephemeral=True)

    @commands.slash_command(
        name="remove",
        description="Remove a Member from the Ticket",
        guild_ids=[guild_id]
    )
    @commands.has_any_role('SF.Team', 'SF.Guardian', 'SF.dev')
    async def remove(self, ctx, member: Option(Member,
                                               description="Which Member you want to remove from the Ticket",
                                               required=True)):
        if "ticket-" in ctx.channel.name or "ticket-closed-" in ctx.channel.name:
            await ctx.channel.set_permissions(member, 
                                              send_messages=False, 
                                              read_messages=False, 
                                              add_reactions=False,
                                              embed_links=False, 
                                              attach_files=False, 
                                              read_message_history=False,
                                              external_emojis=False)
            self.embed = Embed(
                description=f'Removed {member.mention} from this Ticket <#{ctx.channel.id}>! \n Use /add to add a User.',
                color=discord.colour.Color.green())
            await ctx.send(embed=self.embed)
        else:
            self.embed = Embed(description=f'You can only use this command in a Ticket!',
                               color=discord.colour.Color.red())
            await ctx.send(embed=self.embed)

    @commands.slash_command(
        name="delete",
        description="Delete the Ticket",
        guild_ids=[guild_id]
    )
    async def delete_ticket(self, ctx):
        guild = self.bot.get_guild(guild_id)
        log_channel = self.bot.get_channel(log_channel_id)
        ticket_topic = ctx.channel.topic
        cursor.execute(
            """
                SELECT id, user_id
                FROM tickets 
                WHERE concat(user_id, '-', id) = %s
            """,
            (ticket_topic,)
        )
        ticket = cursor.fetchone()
        ticket_user_id = ticket.get("user_id")
        ticket_creator = guild.get_member(int(ticket_user_id))

        cursor.execute(
            """
                DELETE FROM tickets 
                WHERE category_id = %s
                and user_id = %s
            """,
            (ticket_creator,)
        )
        connection.commit()

        # Create Transcript
        military_time: bool = True
        transcript = await chat_exporter.export(
            ctx.channel,
            limit=200,
            tz_info=timezone,
            military_time=military_time,
            bot=self.bot,
        )
        if transcript is None:
            return

        transcript_file = discord.File(
            io.BytesIO(transcript.encode()),
            filename=f"transcript-{ctx.channel.name}.html")
        transcript_file2 = discord.File(
            io.BytesIO(transcript.encode()),
            filename=f"transcript-{ctx.channel.name}.html")

        ticket_creator = guild.get_member(ticket_creator)
        embed = discord.Embed(description=f'Ticket is deliting in 5 seconds.', color=0xff0000)
        transcript_info = discord.Embed(title=f"Ticket Deleting | {ctx.channel.name}",
                                        description=f"Ticket from: {ticket_creator.mention}\nTicket Name: {ctx.channel.name} \n Closed from: {ctx.author.mention}",
                                        color=discord.colour.Color.blue())

        await ctx.reply(embed=embed)
        # Checks if the user has his DMs enabled/disabled
        try:
            await ticket_creator.send(embed=transcript_info, file=transcript_file)
        except:
            transcript_info.add_field(name="Error",
                                      value="Couldn't send the Transcript to the User because he has his DMs disabled!",
                                      inline=True)
        await log_channel.send(embed=transcript_info, file=transcript_file2)
        await asyncio.sleep(3)
        await ctx.channel.delete(reason="Ticket got Deleted!")


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


bot.add_cog(TicketSystem(bot))
bot.add_cog(TicketCommand(bot))
bot.run(bot_token)
