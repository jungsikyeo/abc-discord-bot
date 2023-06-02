#!/usr/bin/python3
import requests
import datetime
import pymysql
import os

import cloudscraper
import json
from dotenv import load_dotenv

load_dotenv()

mysql_ip = os.getenv("MYSQL_IP_DOCKER")
mysql_port = os.getenv("MYSQL_PORT_DOCKER")
mysql_id = os.getenv("MYSQL_ID")
mysql_passwd = os.getenv("MYSQL_PASSWD")
mysql_db = os.getenv("MYSQL_DB")

def today_date():
    today = datetime.datetime.now().date()
    date_string = today.strftime("%Y-%m-%d 00:00:00")
    date_object = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    today_date = str(int(date_object.timestamp()))
    print("today:" + date_string)
    return str(today_date)


def month_date():
    month = (datetime.datetime.now() + datetime.timedelta(days=31)).date()
    date_string = month.strftime("%Y-%m-%d 23:59:59")
    date_object = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    month_date = str(int(date_object.timestamp()))
    print("month:" + date_string)
    return str(month_date) 


def batch_date():
    batch = datetime.datetime.now()
    date_string = batch.strftime("%Y-%m-%d %H:%M:%S")
    date_object = datetime.datetime.strptime(date_string, "%Y-%m-%d %H:%M:%S")
    batch_date = str(int(date_object.timestamp()))
    print("batch:" + date_string)
    return str(batch_date)


def get_project_data(today_timestamp, tomorrow_timestamp):
    scraper = cloudscraper.create_scraper()
    try:
        print(today_timestamp, tomorrow_timestamp)
        headers = {"cookie": "__Host-next-auth.csrf-token=1419d8fd0c5c5b8231034db078e9f88defda6ef8dd5c011e25282b47549485fc%7Ca3172f7f55f479b244f6472e74d9610a27498eaecadb0d7d31a8a8d927c8ea38; __Secure-next-auth.callback-url=https%3A%2F%2Fwww.alphabot.app%2Fdegen-zoo-x-ghouls-bml6u2; CookieConsent=true; __gads=ID=8da0d488c04e22fe-2275d95846da00ec:T=1677615672:RT=1677615672:S=ALNI_MYaqnYqPUHALnAzLbkbhJMAjGz5xQ; _gid=GA1.2.1942091217.1679879916; __gpi=UID=00000bce464649a7:T=1677615672:RT=1680841107:S=ALNI_MbCw5Uf6RxhzIkndj2Omgp4b44plA; __cf_bm=5wIKuTU7qHvMFXRix4hGWSJfXbo_3EPEo0AB0LAJDbI-1680858378-0-ASN+uR2si9jX4z4X3dAI9QW5rQo1bON3jaMfsiPqxqsy66jxm0xIwI3rwfIpLcazUioFCmZhfRdkN03GxQJoO7JbdXeA72Gw6cKYN4vshYw2a4Sdk9Lfl1Zs6V/xYUOd6g==; _ga=GA1.2.19617137.1676810584; __Secure-next-auth.session-token=eyJhbGciOiJkaXIiLCJlbmMiOiJBMjU2R0NNIn0..OO-02a3eYZgSsmzg.GMKRbSPQwNkhMFj8DMi-ilpNITKjI8rwDIak-ZKDUQwLulr3q5wztsJD7nWXkJin2J34yr3419bhZkqba7Uqt4GVmZGzPPwF135J_83PZOQCWi4Dcwl3ESICsRcrgc3oPI9ebnXrXqV6prXNqUxdMCHlRLWQ3QX7LMvLrNbMLKq7vCVf-EnQb8Yc0i7XVjWUUovIX3iBYxGce6UorOqAx9CqCjyQcX1hlSJX82pxRm-RvFHF5Gx6i2Cj1QwRBvSy243FYptWP86dKH38I2ejuFyvCFWrCAOLvbIR6Uh-nYcMIkvsH15Bv2-uqVv8DQJUmAg-DatD-QTh3s0VL6U4Zp35F5XTsJCWVbMLFejoiD19xdZV2-FmlnDnI20EyXMkzqLW7lN9i7qZ5Temci_1tgvkwnmac9nkjhGWxWcKSG63K-2I3O_KinNa8q73-tbZtaSIYOQs1571w2L4ltTxxC9964Chlkgm2rad4J7s-_FJ-n4VibR8fStwxlMkEwQFbRy34uFUUUMDN9-cylh1gi_lIgA9vhHujlgvxe2LrDNiqiVO8W61mkEn2JlxnWVPe0VuTX3dXu6vsvcqLKynfvEsRDDSzcJ4AfUYhnfqcusWNURlvJ6DDdbI914ietaLMQ6cctc36g5euOeMLs_dkTIx_7y3dP6Y7TZX4GR5jVDTk0J--V17tK1OOmk9JHZnyfmdN3SUwEoR2eje2xm5qDCu6iVdo62uZLagXu7WiiQ.lHOSozDRz92RtrCdYgSrJg; _ga_5P3HN827YC=GS1.1.1680855929.250.1.1680858660.0.0.0; mp_e07f9907b6792861d8448bc4004fb2b4_mixpanel=%7B%22distinct_id%22%3A%20%2218669b2f5f1106c-0a7f2bd95c706e-16525635-1d4c00-18669b2f5f21222%22%2C%22%24device_id%22%3A%20%2218669b2f5f1106c-0a7f2bd95c706e-16525635-1d4c00-18669b2f5f21222%22%2C%22%24initial_referrer%22%3A%20%22%24direct%22%2C%22%24initial_referring_domain%22%3A%20%22%24direct%22%7D"}
        response = scraper.get(f"https://www.alphabot.app/api/projectData?calendar=true&startDate={today_timestamp}&endDate={tomorrow_timestamp}&selectedMonth=2&a=0xa1B1ec6eaD8CEfa028Df12609F38EEDAc356a697", headers=headers).text 
        return json.loads(response)
    except Exception as e:
        print("Error:", e)
        return ""


def is_json_key_present(json_data, key):
    try:
        buf = str(json_data[key])
    except Exception as e:
        return ""

    return buf


today_timestamp = today_date() + "000"
month_timestamp = month_date() + "000"
batch_timestamp = batch_date() + "000"
print("")

data = get_project_data(today_timestamp, month_timestamp)

connection = pymysql.connect(
    host=mysql_ip,
    port=int(mysql_port),
    user=mysql_id,
    password=mysql_passwd,
    database=mysql_db,
    charset="utf8mb4",
    cursorclass=pymysql.cursors.DictCursor,
)

try:
    index = 0
    for project in data["projects"]:
        with connection.cursor() as cursor:
            twitter_url = is_json_key_present(project, "twitterUrl")

            select_query = f"SELECT * FROM projects WHERE twitterUrl = '{twitter_url}'"
            cursor.execute(select_query)
            existing_project = cursor.fetchone()

            noUpdate = 0
            if existing_project:
                id = existing_project['id']
                noUpdate = existing_project['noUpdate']
                if noUpdate == None:
                    noUpdate = 0
            else:
                id = is_json_key_present(project, "_id")

            insert_sql = (
                "INSERT INTO projects ("
                + "id, name, discordUrl, twitterUrl, instagramUrl, "
                + "telegramUrl, twitterId, osUrl, twitterBannerImage, twitterProfileImage,"
                + "hasTime, mintDate, mintDateString, supply, wlPrice,"
                + "pubPrice, isWinner, isStarred, mintPhases, blockchain,"
                + "lastUpdated, dateCreated, vetted, denied, starCount,"
                + "batchUpdated"
                + ") VALUES ("
                + "%s, %s, %s, %s, %s,"
                + "%s, %s, %s, %s, %s,"
                + "%s, %s, %s, %s, %s,"
                + "%s, %s, %s, %s, %s,"
                + "%s, %s, %s, %s, %s,"
                + "%s"
                ")"
                + " ON DUPLICATE KEY UPDATE "
                + "name=VALUES(name), discordUrl=VALUES(discordUrl), instagramUrl=VALUES(instagramUrl),"
                + "telegramUrl=VALUES(telegramUrl), twitterId=VALUES(twitterId), osUrl=VALUES(osUrl), twitterBannerImage=VALUES(twitterBannerImage), twitterProfileImage=VALUES(twitterProfileImage),"
                + "hasTime=VALUES(hasTime), mintDate=VALUES(mintDate), mintDateString=VALUES(mintDateString), supply=VALUES(supply), wlPrice=VALUES(wlPrice),"
                + "pubPrice=VALUES(pubPrice), isWinner=VALUES(isWinner), isStarred=VALUES(isStarred),  blockchain=VALUES(blockchain),"
                + "lastUpdated=VALUES(lastUpdated), dateCreated=VALUES(dateCreated), vetted=VALUES(vetted), denied=VALUES(denied), starCount=VALUES(starCount),"
                + "batchUpdated=VALUES(batchUpdated)"
            )

            insert_values = (
                id,
                is_json_key_present(project, "name"),
                is_json_key_present(project, "discordUrl"),
                is_json_key_present(project, "twitterUrl"),
                is_json_key_present(project, "instagramUrl"),
                is_json_key_present(project, "telegramUrl"),
                is_json_key_present(project, "twitterId"),
                is_json_key_present(project, "osUrl"),
                is_json_key_present(project, "twitterBannerImage"),
                is_json_key_present(project, "twitterProfileImage"),
                is_json_key_present(project, "hasTime"),
                is_json_key_present(project, "mintDate"),
                is_json_key_present(project, "mintDateString"),
                is_json_key_present(project, "supply"),
                is_json_key_present(project, "wlPrice"),
                is_json_key_present(project, "pubPrice"),
                is_json_key_present(project, "isWinner"),
                is_json_key_present(project, "isStarred"),
                "",
                is_json_key_present(project, "blockchain"),
                is_json_key_present(project, "lastUpdated"),
                is_json_key_present(project, "dateCreated"),
                is_json_key_present(project, "vetted"),
                is_json_key_present(project, "denied"),
                is_json_key_present(project, "starCount"),
                batch_timestamp,
            )

            if int(noUpdate) < 1:
                cursor.execute(insert_sql, insert_values)
            else:
                print(id, is_json_key_present(project, "name"), " : no update")


            is_winner = is_json_key_present(project, "isWinner")
            if is_winner == "True":
                project_id = id
                regUser = "으노아부지#2642"
                recommend_type = "UP"

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
                cursor.execute(insert_query)

    connection.commit()

except Exception as e:
    print("Error:", e)

finally:
    if connection.open:
        connection.close()

