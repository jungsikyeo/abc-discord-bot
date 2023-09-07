import asyncio
import discord
import os
import pymysql
from discord.ext import commands
from discord.ui import View, button, Select, Modal, InputText
from discord import Embed, ButtonStyle
from dotenv import load_dotenv
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from asyncio import TimeoutError

load_dotenv()
command_flag = os.getenv("SEARCHFI_BOT_FLAG")
bot_token = os.getenv("SHOPPING_BOT_TOKEN")
channel_name = os.getenv("SHOPPING_CHANNEL_NAME")
mysql_ip = os.getenv("MYSQL_IP")
mysql_port = os.getenv("MYSQL_PORT")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")

products_db = {}
user_tokens_db = {}
user_tickets_db = {}


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


class WelcomeView(View):
    def __init__(self, db):
        super().__init__(timeout=None)
        self.db = db

    @button(label="Prizes", style=ButtonStyle.primary)
    async def button_prizes(self, button, interaction):
        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select id, name, image, price 
                from products
            """)
            all_products = cursor.fetchall()
            if not all_products:
                description = "```ℹ️ 응모 가능한 경품이 없습니다.\n\nℹ️ There are no prizes available.```"
                await interaction.response.send_message(description, ephemeral=True)
                return

            await interaction.response.send_message(
                view=ProductSelectView(all_products),
                ephemeral=True
            )
        except Exception as e:
            description = "```❌ 경품을 불러오는 중에 문제가 발생했습니다.\n\n❌ There was a problem while trying to retrieve the prize.```"
            await interaction.response.send_message(description, ephemeral=True)
            print(f"error: {e}")
        finally:
            cursor.close()
            connection.close()

    @button(label="My Tickets", style=ButtonStyle.danger)
    async def button_my_tickets(self, button, interaction):
        user_id = str(interaction.user.id)

        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select p.id, p.name, p.image, p.price, count(p.id) tickets
                from user_tickets u
                inner join products p on u.product_id = p.id
                where u.user_id = %s
                group by p.id, p.name, p.image, p.price
            """, user_id)
            all_user_tickets = cursor.fetchall()
            if not all_user_tickets:
                description = "```ℹ️ 응모한 티켓이 없습니다.\n\nℹ️ There is no ticket you applied for.```"
                await interaction.response.send_message(description, ephemeral=True)
                return

            description = "My tickets:\n\n"
            for user_ticket in all_user_tickets:
                description += f"""`{user_ticket['name']}`     x{user_ticket['tickets']}\n"""
            embed = Embed(title="", description=description, color=0xFFFFFF)
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
        except Exception as e:
            description = "```❌ 응모한 티켓을 불러오는 중에 문제가 발생했습니다.\n\n" \
                          "❌ There was a problem loading the ticket you applied for.```"
            await interaction.response.send_message(description, ephemeral=True)
            print(f"error: {e}")
        finally:
            cursor.close()
            connection.close()

    @button(label="My Tokens", style=ButtonStyle.green)
    async def button_my_tokens(self, button, interaction):
        user_id = str(interaction.user.id)

        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, user_id)
            user = cursor.fetchone()
            if not user:
                user_tokens = 0
            else:
                user_tokens = user['tokens']
            description = "My tokens:\n\n" \
                          f"`{user_tokens}` tokens"
            embed = Embed(title="", description=description, color=0xFFFFFF)
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
        except Exception as e:
            description = "```❌ 데이터 불러오는 중에 문제가 발생했습니다.\n\n❌ There was a problem loading data.```"
            await interaction.response.send_message(description, ephemeral=True)
            print(f"error: {e}")
        finally:
            cursor.close()
            connection.close()


class ProductSelectView(View):
    def __init__(self, all_products):
        super().__init__()
        self.all_products = all_products
        self.options = [discord.SelectOption(label=f"""{product['name']}""", value=product['name']) for product in
                        all_products]
        self.add_item(ProductSelect(self.options, self.all_products))


class ProductSelect(Select):
    def __init__(self, options, all_products):
        super().__init__(placeholder='Please choose a prize', min_values=1, max_values=1, options=options)
        self.all_products = all_products

    async def callback(self, interaction):
        selected_product = None

        for product in self.all_products:
            if product['name'] == self.values[0]:
                selected_product = product
                break

        buy_button_view = BuyButton(selected_product)

        description = "응모하시려면 아래에 `Buy` 버튼을 눌러주세요.\n\nPlease press the `Buy` button below to apply."
        embed = Embed(title=selected_product['name'], description=description, color=0xFFFFFF)
        embed.add_field(name="Price", value=f"```{selected_product['price']} tokens```", inline=True)
        embed.set_image(url=selected_product['image'])

        await interaction.response.send_message(
            embed=embed,
            view=buy_button_view,
            ephemeral=True
        )


class BuyButton(View):
    def __init__(self, product):
        super().__init__()
        self.product = product

    @button(label="Buy", style=discord.ButtonStyle.primary, custom_id="buy_button")
    async def buy(self, button, interaction):
        user_id = str(interaction.user.id)
        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                select id, name, image, price 
                from products
                where id = %s
            """, self.product['id'])
            product = cursor.fetchone()

            if product:
                price = int(product['price'])
            else:
                description = "```❌ 경품을 응모하는 중에 문제가 발생했습니다.\n\n❌ There was a problem applying for the prize.```"
                await interaction.response.send_message(description, ephemeral=True)
                return

            cursor.execute("""
                select tokens
                from user_tokens
                where user_id = %s
            """, user_id)
            user = cursor.fetchone()

            if user:
                user_tokens = int(user['tokens'])
            else:
                user_tokens = 0

            if user_tokens < price:
                description = "```❌ 토큰이 부족합니다.\n\n❌ Not enough tokens.```"
                await interaction.response.send_message(description, ephemeral=True)
                return
            else:
                user_tokens -= price

                cursor.execute("""
                    insert into user_tickets(user_id, product_id)
                    values (%s, %s)
                """, (user_id, product['id']))

                cursor.execute("""
                    update user_tokens set tokens = %s
                    where user_id = %s
                """, (user_tokens, user_id))

                description = f"```✅ `{self.product['name']}` 경품에 응모하였습니다.\n\n" \
                              f"✅ You applied for the `{self.product['name']}` prize.```"
                embed = Embed(title="", description=description, color=0xFFFFFF)
                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True
                )
            connection.commit()
        except Exception as e:
            description = "```❌ 경품을 응모하는 중에 문제가 발생했습니다.\n\n❌ There was a problem applying for the prize.```"
            await interaction.response.send_message(description, ephemeral=True)
            print(f"error: {e}")
            connection.rollback()
        finally:
            cursor.close()
            connection.close()


class ModalAddPrize(Modal):
    def __init__(self, db):
        super().__init__(title="Add Prize")
        self.item_name = InputText(label="Prize Name",
                                   placeholder="Example Prize",
                                   custom_id="name",
                                   max_length=50, )
        self.item_image = InputText(label="Image URL",
                                    placeholder="https://example.com/image.jpg",
                                    custom_id="image", )
        self.item_price = InputText(label="Price",
                                    placeholder="100",
                                    custom_id="price", )
        self.add_item(self.item_name)
        self.add_item(self.item_image)
        self.add_item(self.item_price)
        self.db = db

    async def callback(self, interaction):
        name = self.item_name.value
        image = self.item_image.value
        try:
            price = int(self.item_price.value)
        except Exception as e:
            description = "```❌ 가격은 숫자로 입력해야합니다.\n\n❌ Price must be entered numerically.```"
            await interaction.response.send_message(description, ephemeral=True)
            print(f"error: {e}")
            return

        connection = db.get_connection()
        cursor = connection.cursor()
        try:
            cursor.execute("""
                insert into products (name, image, price)
                values (%s, %s, %s)
            """, (name, image, price))
            description = f"```✅ `{name}`이 등록되었습니다.\n\n✅ '{name}' registered.```"
            embed = Embed(title="", description=description, color=0xFFFFFF)
            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )
            connection.commit()
        except Exception as e:
            connection.rollback()
            description = "```❌ 데이터 불러오는 중에 문제가 발생했습니다.\n\n❌ There was a problem loading data.```"
            await interaction.response.send_message(description, ephemeral=True)
            print(f"error: {e}")
        finally:
            cursor.close()
            connection.close()


bot = commands.Bot(command_prefix=command_flag, intents=discord.Intents.all())
db = Database(mysql_ip, mysql_port, mysql_id, mysql_passwd, mysql_db)


async def is_reservation_channel(ctx):
    return ctx.channel.name == channel_name


@bot.command()
@commands.check(is_reservation_channel)
async def start(ctx):
    description = "ShoppingFi에 오신 것을 환영합니다!\n\n" \
                  "SearchFi가 준비한 경품 추첨에 SearchFi 토큰으로 참여할 수 있습니다.\n\n" \
                  "`Prizes` 버튼을 클릭하면 경품이 표시됩니다.\n\n" \
                  "`My Tickets` 버튼을 클릭하면 내가 참여한 경품을 확인할 수 있습니다.\n\n\n" \
                  "Welcome to ShoppingFi!\n\n" \
                  "You can participate in the raffle of prizes prepared by SearchFi with your SearchFi Token.\n\n" \
                  "Click on the `Prizes` button to see the prize.\n\n" \
                  "Click the `My Tickets` button to check out the prizes I participated in."

    embed = Embed(title="🎁 SearchFi Shop 🎁", description=description, color=0xFFFFFF)
    embed.set_image(
        url="https://media.discordapp.net/attachments/1069466892101746740/1148837901422035006/3c914e942de4d39a.gif?width=1920&height=1080")
    embed.set_footer(text="Powered by 으노아부지#2642")

    view = WelcomeView(db)

    await ctx.send(embed=embed, view=view)


@bot.slash_command(
    name='add_prize',
    description='Add Prizes command in ShoppingFi.',
    default_permission=True
)
@commands.has_any_role('SF.Team')
async def add_prize(interaction):
    modal = ModalAddPrize(db)
    try:
        await interaction.response.send_modal(modal=modal)
        await asyncio.sleep(10)
    except TimeoutError:
        await interaction.response.send_message("Error: timeout", ephemeral=True)


bot.run(bot_token)
