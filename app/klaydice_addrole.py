import requests
import gspread
import time
import os
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# 디렉토리 생성
log_directory = "./klaydice_addrole"
if not os.path.exists(log_directory):
    os.makedirs(log_directory)

# 환경 변수로부터 토큰을 가져옵니다.
discord_api_token = os.getenv("SEARCHFI_BOT_TOKEN")

# 구글시트 설정
sheet_name = "klaydice role"
file_name = "searchfi.json"

# 서버(길드) 정보 (서치파이: 961242951504261130 / 1073551537940476007, 으노아부지: 1069466891367751691 / 1117874376289824778)
guild_id = "961242951504261130"
role_id = "1073551537940476007"

# 구글 시트에서 데이터를 가져오는 함수
def fetch_sheet_data():
    sheet_data = {}
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name(file_name, scope)
    client = gspread.authorize(creds)
    sheet = client.open(sheet_name).sheet1
    records = sheet.get_all_records()

    for record in records:
        if 'discord_uid' in record:
            sheet_data[str(record['discord_uid'])] = str(record['discord_uid'])

    return sheet_data

# 전체 회원 목록을 가져오는 함수
def fetch_all_members():
    members = []
    headers = {
        "Authorization": f"Bot {discord_api_token}",
        "User-Agent": "DiscordBot (https://github.com/jungsikyeo/abc-discord-bot, v0.1)",
    }
    after = 0  # 시작하는 회원 ID (가장 처음은 0)

    while True:
        if after == 0:
            url = f"https://discord.com/api/v10/guilds/{guild_id}/members?limit=1000"
        else:
            url = f"https://discord.com/api/v10/guilds/{guild_id}/members?limit=1000&after={after}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"Failed to get members: {response.content}")

        data = json.loads(response.content)
        if not data:
            break

        members.extend(data)
        after = data[-1]['user']['id']
        time.sleep(1)

    return members

MAX_RETRIES = 2  # 최대 재시도 횟수

# 롤을 관리하는 함수
def manage_roles(all_members, sheet_data, log_file):
    for member in all_members:
        uid = member['user']['id']
        current_roles = set(member['roles'])
        sheet_entry = sheet_data.get(uid, "")

        time.sleep(1)  # API rate-limiting

        print(f"{uid} Search....")
        log_file.write(f"{uid} Search....\n")

        retries = 0
        while retries < MAX_RETRIES:
            try:
                if sheet_entry:
                    if role_id not in current_roles:
                        # Add role
                        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}/roles/{role_id}"
                        headers = {"Authorization": f"Bot {discord_api_token}"}
                        response = requests.put(url, headers=headers)
                        if response.status_code == 204:
                            print(f"Role added for UID {uid}\n")
                            log_file.write(f"Role added for UID {uid}\n\n")
                            break  # 성공하면 반복 종료
                        else:
                            print(f"Failed to add role for UID {uid}. Retrying...")
                            log_file.write(f"Failed to add role for UID {uid}. Retrying...\n")
                    else:
                        print(f"{uid} is already having role\n")
                        log_file.write(f"{uid} is already having role\n\n")
                        break
                else:
                    if role_id in current_roles:
                        # Remove role
                        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{uid}/roles/{role_id}"
                        headers = {"Authorization": f"Bot {discord_api_token}"}
                        response = requests.delete(url, headers=headers)
                        if response.status_code == 204:
                            print(f"Role removed for UID {uid}\n")
                            log_file.write(f"Role removed for UID {uid}\n\n")
                            break  # 성공하면 반복 종료
                        else:
                            print(f"Failed to remove role for UID {uid}. Retrying...")
                            log_file.write(f"Failed to remove role for UID {uid}. Retrying...\n")
                    else:
                        print(f"{uid} is not target\n")
                        log_file.write(f"{uid} is not target\n\n")
                        break
                retries += 1  # 재시도 횟수 증가
            except Exception as e:
                print(f"An error occurred for UID {uid}: {str(e)}. Retrying...")
                log_file.write(f"An error occurred for UID {uid}: {str(e)}. Retrying...\n")
                retries += 1  # 재시도 횟수 증가

# Main Execution
current_date = datetime.now().strftime("%Y%m%d")
log_file_name = f"{log_directory}/klaydice_addrole_{current_date}.txt"

with open(log_file_name, "w") as log_file:
    try:
        sheet_data = fetch_sheet_data()
        all_members = fetch_all_members()
        manage_roles(all_members, sheet_data, log_file)
    except Exception as e:
        print(f"An error occurred: {str(e)}\n")
        log_file.write(f"An error occurred: {str(e)}\n")
