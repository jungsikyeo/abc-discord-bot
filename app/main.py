import requests
import os
import uuid
import pymysql
import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from pymysql.cursors import DictCursor
from dbutils.pooled_db import PooledDB
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


class Database:
    def __init__(self, host, user, password, db):
        self.pool = PooledDB(
            creator=pymysql,
            maxconnections=5,
            mincached=2,
            host=host,
            user=user,
            password=password,
            database=db,
            charset='utf8mb4',
            cursorclass=DictCursor
        )
    
    def get_connection(self):
        return self.pool.connection()

class Queries:
    def update_count(db, count_type, project_id, dc_id):
        select_query = ""
        select_query = select_query + f"update projects set {count_type} = ifnull(nullif({count_type},0),0)+1 where id = '{project_id}' "

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                conn.commit()
                return Queries.select_count(db, count_type, project_id, dc_id)

    def select_count(db, count_type, project_id, dc_id):
        select_query = ""
        select_query = select_query + f"select {count_type} from projects where id = '{project_id}' "

        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchone()
                return result

    def insert_project(db, uuid, form):
        name = form["name"]
        twitterUrl = form["twitterUrl"]
        twitterProfileImage = form["twitterProfileImage"]
        mintDate = form["mintDate"]
        supply = form["supply"]
        wlPrice = form["wlPrice"]
        pubPrice = form["pubPrice"]
        blockchain = form["blockchain"]
        regUser = form["regUser"]

        insert_query = f"""
            insert into projects
            (
                id, name, twitterUrl, twitterProfileImage, mintDate, 
                supply, wlPrice, pubPrice, blockchain, hasTime, 
                regUser, isAlphabot, lastUpdated, dateCreated
            ) 
            values 
            (
                '{uuid}', '{name}', '{twitterUrl}', '{twitterProfileImage}', concat(cast(UNIX_TIMESTAMP('{mintDate}') as char),'000'), 
                '{supply}', '{wlPrice}', '{pubPrice}', '{blockchain}', 'True', 
                '{regUser}', 'N', concat(cast(UNIX_TIMESTAMP() as char),'000'), concat(cast(UNIX_TIMESTAMP() as char),'000')
            )
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}
    
    def update_project(db, form):
        id = form["id"]
        name = form["name"]
        twitterUrl = form["twitterUrl"]
        twitterProfileImage = form["twitterProfileImage"]
        mintDate = form["mintDate"]
        supply = form["supply"]
        wlPrice = form["wlPrice"]
        pubPrice = form["pubPrice"]
        blockchain = form["blockchain"]
        regUser = form["regUser"]

        update_query = f"""
            update projects set
                name = '{name}', twitterUrl = '{twitterUrl}', twitterProfileImage = '{twitterProfileImage}', mintDate = concat(cast(UNIX_TIMESTAMP('{mintDate}') as char),'000'), 
                supply = '{supply}', wlPrice = '{wlPrice}', pubPrice = '{pubPrice}', blockchain = '{blockchain}',  
                lastUpdated = concat(cast(UNIX_TIMESTAMP() as char),'000')
            where id = '{id}'
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(update_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}
    
    def delete_project(db, form):
        id = form["id"]

        delete_query = f"""
            delete from projects
            where id = '{id}'
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(delete_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}

    def select_user_projects(db, reg_user):
        select_query = f"""
            SELECT
                id, 
                name, 
                discordUrl,
                twitterUrl,  
                twitterProfileImage,  
                supply,  
                wlPrice,  
                pubPrice,  
                blockchain,  
                FROM_UNIXTIME(mintDate/1000, '%Y-%m-%dT%H:%i') mintDate,
                regUser  
             FROM projects 
             WHERE 1=1 
             AND regUser = '{reg_user}' 
             ORDER BY name ASC 
        """
        with db.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(select_query)
                result = cursor.fetchall()
                return 
                
    def merge_recommend(db, project_id, regUser, recommend_type):
        insert_query = f"""
            insert into recommends
            (
                projectId, regUser, recommendType
            ) 
            values 
            (
                '{project_id}', '{regUser}', '{recommend_type}'
            )
            ON DUPLICATE KEY UPDATE recommendType='{recommend_type}';
        """
        try:
            with db.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(insert_query)
                    conn.commit()
            return {"status":"OK"}
        except Exception as e:
            conn.rollback()
            print(e)
            return {"status": "ERROR", "msg": e}
 
app = FastAPI()
db = Database("172.27.0.2", "bot", "y20431", "alphabot")

@app.get("/")
def read_root():
    return ""

@app.get("/good/{project_id}/{dc_id}")
def good_item(project_id: str, dc_id: str):
    result = Queries.merge_recommend(db, project_id, dc_id, 'UP')
    html = """
    <html>
        <script>
            alert("It's been recommended.");
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=html)

@app.get("/bad/{project_id}/{dc_id}")
def good_item(project_id: str, dc_id: str):
    result = Queries.merge_recommend(db, project_id, dc_id, 'DOWN')
    html = """
    <html>
        <script>
            alert("It's not recommended.");
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=html)

app.mount("/static", StaticFiles(directory="/code/app/static"), name="static")
templates = Jinja2Templates(directory="/code/app/templates")

DISCORD_CLIENT_ID = "1069463768247050321"
DISCORD_CLIENT_SECRET = "cJHM69WsrLjlEqgkii1rNfy2cICOtLWW"
DISCORD_REDIRECT_URI = "https://code.yjsdev.tk/discord-callback"

@app.get("/discord-callback/register")
async def reg_discord_callback(request: Request, code: str):
    try:
        headers = { 
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{DISCORD_REDIRECT_URI}/register",
            "scope": "identify"
        }
        response = requests.post("https://discord.com/api/oauth2/token", headers=headers, data=data)
        response.raise_for_status()
        access_token = response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get("https://discord.com/api/users/@me", headers=headers)
        response.raise_for_status()
        user = response.json()

        today = datetime.datetime.now().date()
        date_string = today.strftime("%Y-%m-%d")
        return templates.TemplateResponse("register.html", {"request": request, "user": user, "today": date_string})
    except Exception as e:
        print(e)
        return templates.TemplateResponse("error.html", {"request": request})

@app.get("/discord-callback/modify")
async def modify_discord_callback(request: Request, code: str):
    try:
        headers = { 
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": f"{DISCORD_REDIRECT_URI}/modify",
            "scope": "identify"
        }
        response = requests.post("https://discord.com/api/oauth2/token", headers=headers, data=data)
        response.raise_for_status()
        access_token = response.json()["access_token"]
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get("https://discord.com/api/users/@me", headers=headers)
        response.raise_for_status()
        user = response.json()
        print(f"{user['username']}#{user['discriminator']}")
        result = Queries.select_user_projects(db, f"{user['username']}#{user['discriminator']}")
        
        today = datetime.datetime.now().date()
        date_string = today.strftime("%Y-%m-%d")
        return templates.TemplateResponse("modify.html", {"request": request, "user": user, "projects": result, "today": date_string})
    except Exception as e:
        print(e)
        return templates.TemplateResponse("error.html", {"request": request})
        
@app.post("/regist")
async def regist_submit(request: Request):
    unique_id = uuid.uuid4()
    form_data = await request.form()
    result = Queries.insert_project(db, unique_id, form_data)
    if result["status"] == "OK":
        comment = "Registration completed!"
    else:
        comment = "Registration error!"
        
    html = f"""
    <html>
        <script>
            parent.winClose('{comment}')
        </script>
    </html>
    """
    return HTMLResponse(content=html)

@app.post("/update")
async def update_submit(request: Request):
    form_data = await request.form()
    result = Queries.update_project(db, form_data)
    if result["status"] == "OK":
        comment = "Update completed!"
    else:
        comment = "Update error!"
        
    html = f"""
    <html>
        <script>
            parent.winClose('{comment}')
        </script>
    </html>
    """
    
    return HTMLResponse(content=html)

@app.post("/delete")
async def delete_submit(request: Request):
    form_data = await request.form()
    result = Queries.delete_project(db, form_data)
    if result["status"] == "OK":
        comment = "Delete completed!"
    else:
        comment = "Delete error!"
        
    html = f"""
    <html>
        <script>
            parent.winClose('{comment}')
        </script>
    </html>
    """
    return HTMLResponse(content=html)

