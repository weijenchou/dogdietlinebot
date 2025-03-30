from flask import Flask, request, abort, render_template, redirect, url_for
import os
import logging
import pandas as pd
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, MessagingApiBlob, ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
import sqlite3
from datetime import datetime
import daily_calories
import packageOCR
import dogdietyolo
import petmap
from dotenv import load_dotenv
import re
from linebot.v3.messaging import QuickReply, QuickReplyItem, CameraAction, CameraRollAction, MessageAction
import tempfile
from ultralytics import YOLO
from google.cloud import vision
from google.oauth2 import service_account
import requests
import json
import time
import threading

app = Flask(__name__)

# 設置日誌
logging.basicConfig(level=logging.INFO)

# 載入環境變數
load_dotenv('information.env')
API_KEY = os.getenv("GOOGLE_MAP_API_KEY")
if not API_KEY:
    raise ValueError("GOOGLE_MAP_API_KEY not found in environment variables.")

# 檢查 LINE Bot 的環境變數
ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
channel_secret = os.getenv('LINE_CHANNEL_SECRET')
if not ACCESS_TOKEN or not channel_secret:
    raise ValueError("LINE_CHANNEL_ACCESS_TOKEN or LINE_CHANNEL_SECRET not found in environment variables.")

configuration = Configuration(access_token=ACCESS_TOKEN)
handler = WebhookHandler(channel_secret)

# 全局初始化 Google Cloud Vision 客戶端
google_api_key_path = os.getenv('GOOGLE_Translation_API_KEY')
if not google_api_key_path or not os.path.exists(google_api_key_path):
    raise ValueError("Google API key path not found or invalid in environment variables.")
credentials = service_account.Credentials.from_service_account_file(google_api_key_path)
vision_client = vision.ImageAnnotatorClient(credentials=credentials)

# 讀取 dog_breeds.csv 文件
dog_breeds_df = pd.read_csv('dog_breeds.csv')
breeds = dog_breeds_df['breed_name'].tolist()
statuses = [
    '正在發育的幼犬(4個月以下)', 
    '正在發育的幼犬(4個月-1歲)', 
    '結紮成年犬(1-7歲)', 
    '未結紮成年犬(1-7歲)', 
    '輕度減肥成年犬', 
    '重度減肥成年犬', 
    '過瘦成年犬', 
    '輕度活動量', 
    '劇烈活動量', 
    '高齡犬', 
    '懷孕中的狗媽媽', 
    '哺乳中的狗媽媽', 
    '生病成年犬'
]

# 載入 YOLO 模型
model_path = "best.pt"
yolo_model = dogdietyolo.load_yolo_model(model_path)
if yolo_model is None:
    raise Exception("無法載入 YOLO 模型，請檢查模型檔案是否存在！")

welcome_message = """嗨嗨！我是你的寵物飲食小助手 🐾
想幫毛孩做什麼呢？😉

👇 直接點下方圖文選單開始啦 👇
✨ 請先完成「新增寵物檔案」哦！✨

更多功能在這兒，快輸入數字看看吧！
----------------------
1. 不可食用食物 🚫
2. 保健建議 💡
3. 拍包裝算熱量 📸
4. 拍鮮食算熱量 🍲
----------------------
隨時輸入「退出」回到這裡哦 🏠"""

# 用於暫存用戶狀態
user_states = {}

# 函數：從 ngrok API 獲取公開 URL
def get_ngrok_url():
    try:
        response = requests.get("http://localhost:4040/api/tunnels")
        data = response.json()
        for tunnel in data['tunnels']:
            if tunnel['proto'] == 'https':
                return tunnel['public_url']
        return None
    except Exception as e:
        app.logger.error(f"無法獲取 ngrok URL: {str(e)}")
        return None

#https://0cab-220-132-199-24.ngrok-free.app
# 初始化 global_base_url
global_base_url = get_ngrok_url() or os.getenv("BASE_URL", "https://0cab-220-132-199-24.ngrok-free.app")
app.logger.info(f"Initial global_base_url: {global_base_url}")

# 定時更新 global_base_url
def update_base_url_periodically():
    global global_base_url
    while True:
        new_url = get_ngrok_url()
        if new_url and new_url != global_base_url:
            global_base_url = new_url
            app.logger.info(f"Updated global_base_url to: {global_base_url}")
        time.sleep(300)  # 每 5 分鐘檢查一次

# 啟動背景執行緒來定時更新 global_base_url
threading.Thread(target=update_base_url_periodically, daemon=True).start()

# API 端點：手動更新 global_base_url
@app.route('/update_base_url', methods=['POST'])
def update_base_url():
    global global_base_url
    new_base_url = request.form.get('base_url')
    if not new_base_url:
        return "缺少 base_url 參數", 400
    global_base_url = new_base_url
    app.logger.info(f"Updated global_base_url to: {global_base_url}")
    return "global_base_url 已更新", 200

# 初始化 SQLite 資料庫（根據 user_id）
def init_db(user_id):
    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()

    # 創建 dogs 表（如果不存在）
    c.execute('''CREATE TABLE IF NOT EXISTS dogs (
        name TEXT PRIMARY KEY,
        birthday TEXT,
        weight REAL
    )''')

    # 檢查並添加 breed 欄位
    c.execute("PRAGMA table_info(dogs)")
    columns = [col[1] for col in c.fetchall()]
    if 'breed' not in columns:
        c.execute("ALTER TABLE dogs ADD COLUMN breed TEXT")
        print(f"Added 'breed' column to dogs table for user {user_id}")

    # 檢查並添加 status 欄位
    if 'status' not in columns:
        c.execute("ALTER TABLE dogs ADD COLUMN status TEXT")
        print(f"Added 'status' column to dogs table for user {user_id}")

    # 創建 daily_records 表（如果不存在）
    c.execute('''CREATE TABLE IF NOT EXISTS daily_records (
        name TEXT,
        date TEXT,
        calories REAL,
        water REAL,
        FOREIGN KEY (name) REFERENCES dogs (name),
        PRIMARY KEY (name, date)
    )''')

    conn.commit()
    conn.close()

# 查詢所有寵物資料（根據 user_id）
def get_all_dogs(user_id):
    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    c.execute("SELECT name, birthday, weight, breed, status FROM dogs")
    results = c.fetchall()
    conn.close()
    dogs = []
    for result in results:
        name, birthday, weight, breed, status = result
        birth_date = datetime.strptime(birthday, '%Y-%m-%d')
        age = (datetime.now() - birth_date).days // 365
        dogs.append((name, birthday, weight, breed, status, age))
    return dogs

# 查詢寵物基本資料並計算年齡（根據 user_id）
def get_dog_data(user_id, name):
    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    c.execute("SELECT name, birthday, weight, breed, status FROM dogs WHERE name = ?", (name,))
    result = c.fetchone()
    conn.close()
    if result:
        name, birthday, weight, breed, status = result
        birth_date = datetime.strptime(birthday, '%Y-%m-%d')
        age = (datetime.now() - birth_date).days // 365
        return name, birthday, weight, breed, status, age
    return None

# 根據品種名稱查詢健康資訊
def get_health_info(breed_name):
    breed_data = dog_breeds_df[dog_breeds_df['breed_name'] == breed_name]
    if not breed_data.empty:
        row = breed_data.iloc[0]
        return {
            'height': row['height'],
            'weight': row['weight'],
            'lifespan': row['lifespan'],
            'recommended_tests': row['recommended_tests']
        }
    return None

# 儲存寵物基本資料到資料庫（根據 user_id）
def save_dog_data(user_id, name, birthday, weight, breed=None, status=None):
    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO dogs (name, birthday, weight, breed, status) VALUES (?, ?, ?, ?, ?)", 
              (name, birthday, weight, breed, status))
    conn.commit()
    conn.close()

# 儲存每日紀錄到資料庫（根據 user_id）
def save_daily_record(user_id, name, calories, water):
    today = datetime.now().strftime('%Y-%m-%d')
    calories = int(calories)  # 轉為整數
    water = int(water)  # 轉為整數
    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO daily_records (name, date, calories, water) VALUES (?, ?, ?, ?)",
              (name, today, calories, water))
    conn.commit()
    conn.close()

# 查詢每日紀錄（根據 user_id）
def get_daily_record(user_id, name):
    today = datetime.now().strftime('%Y-%m-%d')
    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    c.execute("SELECT calories, water FROM daily_records WHERE name = ? AND date = ?", (name, today))
    result = c.fetchone()
    conn.close()
    if result:
        calories, water = result
        return int(calories), int(water)  # 確保從資料庫讀取的數值為整數
    return None

# 根據品種名稱查詢飲食建議
def get_diet_recommendation(breed_name):
    breed_data = dog_breeds_df[dog_breeds_df['breed_name'] == breed_name]
    if not breed_data.empty:
        row = breed_data.iloc[0]
        return (f"🐶 品種: {row['breed_name']}\n\n"
                f"📏 身高: {row['height']}\n\n"
                f"⚖️ 體重: {row['weight']}\n\n"
                f"⏳ 壽命: {row['lifespan']}\n\n"
                f"❤️ 健康狀況: {row['health']}\n\n"
                f"🩺 建議檢查: {row['recommended_tests']}\n\n"
                f"🍽️ 餵什麼: {row['what_to_feed']}\n\n"
                f"🥄 如何餵養: {row['how_to_feed']}\n\n"
                f"💡 營養建議: {row['nutritional_tips']}")
    return f"未找到 '{breed_name}' 的相關資訊。"

# LINE Bot 回調路由
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.info("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    return 'OK'

# 處理 LINE 文字訊息
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event):
    user_input = event.message.text.strip()
    user_id = event.source.user_id
    app.logger.info(f"Received text message: {user_input} from user {user_id}")

    # 初始化該使用者的資料庫
    init_db(user_id)

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # 定義 Quick Reply 按鈕（相機和相簿）
        quick_reply = QuickReply(items=[
            QuickReplyItem(action=CameraAction(label="開啟相機")),
            QuickReplyItem(action=CameraRollAction(label="從相簿選擇"))
        ])

        # 檢查是否輸入「退出」
        if user_input == "退出":
            if user_id in user_states:
                del user_states[user_id]  # 清除用戶狀態
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=welcome_message)])
            )
            app.logger.info("User exited, sent welcome message")
            return

        # 檢查用戶是否處於某個操作狀態
        if user_id in user_states:
            state = user_states[user_id]
            
            # 選項 1：等待輸入狗狗資料
            if state.get('step') == 'awaiting_dog_info':
                try:
                    lines = user_input.split('\n')
                    name = lines[0].split('：')[1].strip()
                    birthday = lines[1].split('：')[1].strip()
                    weight = float(lines[2].split('：')[1].strip().replace('公斤', '').strip())
                    birth_date = datetime.strptime(birthday, '%Y-%m-%d')
                    age = (datetime.now() - birth_date).days // 365
                    reply = (f"🐶 狗狗的名字：{name}\n"
                             f"🎂 狗狗的生日：{birthday}\n"
                             f"⚖️ 狗狗的體重：{weight}公斤\n"
                             f"🎈 狗狗的年齡：{age}\n"
                             "資料是否儲存？(Y/N)")
                    user_states[user_id] = {'step': 'awaiting_save_confirmation', 'data': (name, birthday, weight)}
                except Exception as e:
                    reply = "輸入格式錯誤，請按照以下格式重新輸入：\n名字：XXX\n生日：YYYY-MM-DD\n體重：XX公斤"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))

            # 選項 1：確認是否儲存
            elif state.get('step') == 'awaiting_save_confirmation':
                if user_input.upper() == 'Y':
                    name, birthday, weight = state['data']
                    save_dog_data(user_id, name, birthday, weight)
                    reply = "資料已儲存！請透過圖文選單中的「建立狗狗檔案」來補充品種和狀態資訊。"
                elif user_input.upper() == 'N':
                    reply = "資料未儲存。"
                else:
                    reply = "請輸入 Y 或 N"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                del user_states[user_id]

            # 選項 2：等待查詢狗狗名字
            elif state.get('step') == 'awaiting_dog_name':
                dog_data = get_dog_data(user_id, user_input)
                if dog_data:
                    name, birthday, weight, breed, status, age = dog_data
                    reply = (f"🐶 狗狗的名字：{name}\n"
                             f"🎂 狗狗的生日：{birthday}\n"
                             f"⚖️ 狗狗的體重：{weight}公斤\n"
                             f"🎈 狗狗的年齡：{age}")
                    if breed and status:
                        reply += f"\n🐾 品種：{breed}\n📊 狀態：{status}"
                else:
                    reply = f"未找到名為 '{user_input}' 的狗狗資料，請確認是否完成設定1。"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                del user_states[user_id]

            # 選項 3：等待輸入狗狗名字和狀態
            elif state.get('step') == 'awaiting_nutrition_info':
                try:
                    lines = user_input.split('\n')
                    name = lines[0].split('：')[1].strip()
                    status = lines[1].split('：')[1].strip()
                    if status not in [str(i) for i in range(1, 14)]:
                        reply = "狀態選擇錯誤，請輸入 1-13 的數字。"
                    else:
                        dog_data = get_dog_data(user_id, name)
                        if dog_data:
                            _, birthday, weight, _, _, _ = dog_data
                            rer = daily_calories.calculate_RER(weight)
                            af_min, af_max = daily_calories.get_AF_for_status(status)
                            der_min = daily_calories.calculate_DER(rer, af_min)
                            der_max = daily_calories.calculate_DER(rer, af_max)
                            min_water, max_water = daily_calories.calculate_water_intake(weight)
                            reply = (f"今日目標\n\n"
                                     f"🐶 狗狗的名字：{name}\n"
                                     f"⚖️ 體重：{weight}公斤\n"
                                     f"🔥 基礎能量需求(RER)：{rer:.2f} kcal\n"
                                     f"⚡ 日常能量需求(DER)：{der_min:.2f}-{der_max:.2f} kcal\n"
                                     f"💧 每日喝水量：{min_water:.2f}-{max_water:.2f} ml")
                        else:
                            reply = f"未找到名為 '{name}' 的狗狗資料，請確認是否完成設定1。"
                    line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                    del user_states[user_id]
                except Exception as e:
                    reply = "輸入格式錯誤，請按照以下格式重新輸入：\n名字：XXX\n狀態：X（1-13 的數字）"
                    line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))

            # 選項 5：等待輸入狗狗品種
            elif state.get('step') == 'awaiting_breed_name':
                reply = get_diet_recommendation(user_input)
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                del user_states[user_id]

            # 選項 6：等待輸入每日紀錄（移除 poop）
            elif state.get('step') == 'awaiting_daily_record':
                try:
                    lines = user_input.split('\n')
                    name = lines[0].split('：')[1].strip()
                    calories = float(lines[1].split('：')[1].strip().replace('卡路里', '').strip())
                    water = float(lines[2].split('：')[1].strip().replace('毫升', '').strip())
                    reply = (f"🔥 熱量：{calories} 卡路里\n"
                             f"💧 水：{water} 毫升\n"
                             "資料是否儲存？(Y/N)")
                    user_states[user_id] = {'step': 'awaiting_record_confirmation', 'data': (name, calories, water)}
                except Exception as e:
                    reply = "輸入格式錯誤，請按照以下格式重新輸入：\n名字：XXX\n卡路里：XX\n水：XX毫升"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))

            # 選項 6：確認是否儲存每日紀錄（移除 poop）
            elif state.get('step') == 'awaiting_record_confirmation':
                if user_input.upper() == 'Y':
                    name, calories, water = state['data']
                    save_daily_record(user_id, name, calories, water)
                    reply = "資料已儲存！"
                elif user_input.upper() == 'N':
                    reply = "資料未儲存。"
                else:
                    reply = "請輸入 Y 或 N"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                del user_states[user_id]

            # 選項 7：等待查詢每日紀錄（移除 poop）
            elif state.get('step') == 'awaiting_daily_record_check':
                record = get_daily_record(user_id, user_input)
                if record:
                    calories, water = record
                    reply = (f"今日已完成\n\n"
                             f"🔥 熱量：{calories} 卡路里\n"
                             f"💧 水量：{water} 毫升")
                else:
                    reply = f"未找到名為 '{user_input}' 的狗狗今日紀錄。"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                del user_states[user_id]

            # 選項 8：等待輸入餵食克數
            elif state.get('step') == 'awaiting_feeding_weight':
                try:
                    grams = float(user_input.strip().replace('克', ''))
                    nutrition_info = state['nutrition_info']
                    total_weight = 1000  # 預設整包為 1 公斤 (1000 克)
                    ratio = grams / total_weight
                    calories = float(nutrition_info.get('熱量', 0)) * ratio
                    protein = float(nutrition_info.get('蛋白質', 0)) 
                    fat = float(nutrition_info.get('脂肪', 0)) 
                    fiber = float(nutrition_info.get('纖維', 0))
                    carbs = float(nutrition_info.get('碳水', 0))
                    water = float(nutrition_info.get('水', 0)) 
                    reply = (f"🔥 熱量：{calories:.2f} kcal\n"
                            f"🥚 蛋白質：{protein:.2f}%\n"
                            f"🧈 脂肪：{fat:.2f}%\n"
                            f"🌾 纖維：{fiber:.2f}%\n"
                            f"🍚 碳水化合物：{carbs:.2f}%\n"
                            f"💧 水分：{water:.2f}%")
                except Exception as e:
                    reply = "請輸入有效的克數（例如：100 或 100克）"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
                del user_states[user_id]

            # 選項 10：選擇查詢方式
            elif state.get('step') == 'awaiting_restaurant_choice':
                if user_input == "目前位置":
                    lat, lon, location_msg = petmap.get_location(API_KEY, choice='1')
                    if lat is None or lon is None:
                        reply = location_msg
                    else:
                        places = petmap.search_nearby_places(API_KEY, lat, lon, max_count=20, place_type=['dog_cafe', 'cat_cafe', 'restaurant'])
                        if places:
                            reply = f"\n找到以下餐廳：\n"
                            for place in places:
                                if place.get('allowsDogs', False):
                                    place_location = place.get('location', {})
                                    place_lat = place_location.get('latitude')
                                    place_lon = place_location.get('longitude')
                                    navigation_url = f"https://www.google.com/maps/dir/?api=1&destination={place_lat},{place_lon}"
                                    reply += f"🍴 餐廳: {place.get('displayName', {}).get('text', '未知')}\n"
                                    reply += f"⭐ 評分: {place.get('rating', '無評分')}\n"
                                    reply += f"📍 地址: {place.get('formattedAddress', '地址未知')}\n"
                                    reply += f"🛣️ 導航: {navigation_url}\n\n"
                        else:
                            reply = f"{location_msg}\n未找到符合條件的餐廳。"
                    line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply.strip())]))
                    del user_states[user_id]
                elif user_input == "輸入地標名稱":
                    reply = "請輸入地標名稱"
                    user_states[user_id] = {'step': 'awaiting_landmark_name'}
                else:
                    reply = "請輸入 1 或 2 選擇查詢方式。"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))

            # 選項 10：等待輸入地標名稱
            elif state.get('step') == 'awaiting_landmark_name':
                lat, lon, location_msg = petmap.get_location(API_KEY, choice='2', place_name=user_input)
                if lat is None or lon is None:
                    reply = location_msg
                else:
                    places = petmap.search_nearby_places(API_KEY, lat, lon, max_count=20, place_type=['dog_cafe', 'cat_cafe', 'restaurant'])
                    if places:
                        reply = f"{location_msg}\n找到以下餐廳：\n"
                        for place in places:
                            if place.get('allowsDogs', False):
                                place_location = place.get('location', {})
                                place_lat = place_location.get('latitude')
                                place_lon = place_location.get('longitude')
                                navigation_url = f"https://www.google.com/maps/dir/?api=1&destination={place_lat},{place_lon}"
                                reply += f"🍴 餐廳: {place.get('displayName', {}).get('text', '未知')}\n"
                                reply += f"⭐ 評分: {place.get('rating', '無評分')}\n"
                                reply += f"📍 地址: {place.get('formattedAddress', '地址未知')}\n"
                                reply += f"🛣️ 導航: {navigation_url}\n\n"
                    else:
                        reply = f"{location_msg}\n未找到符合條件的餐廳。"
                line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply.strip())]))
                del user_states[user_id]

            app.logger.info("Replied with state-specific message")
            return

        # 初始選項處理：處理圖文選單觸發的文字訊息，並回覆帶有 URL 的訊息
        if user_input == "新增寵物檔案":
            reply = f"請點擊以下連結來新增寵物檔案：\n{global_base_url}/create_dog_profile?user_id={user_id}"
        elif user_input == "狗狗檔案":
            reply = f"請點擊以下連結來查看狗狗檔案：\n{global_base_url}/dog_profile?user_id={user_id}"
        elif user_input == "紀錄今日攝取":
            reply = f"請點擊以下連結來記錄今日攝取：\n{global_base_url}/record_daily_intake?user_id={user_id}"
        elif user_input == "33333":
            reply = ("請輸入狗狗的名字：\n"
                     "狗狗的狀態：\n"
                     "1. 正在發育的幼犬(4個月以下)\n"
                     "2. 正在發育的幼犬(4個月-1歲)\n"
                     "3. 結紮成年犬(1-7歲)\n"
                     "4. 未結紮成年犬(1-7歲)\n"
                     "5. 輕度減肥成年犬\n"
                     "6. 重度減肥成年犬\n"
                     "7. 過瘦成年犬\n"
                     "8. 輕度活動量\n"
                     "9. 劇烈活動量\n"
                     "10. 高齡犬\n"
                     "11. 懷孕中的狗媽媽\n"
                     "12. 哺乳中的狗媽媽\n"
                     "13. 生病成年犬\n"
                     "請輸入狗狗目前的狀態(輸入對應數字)：\n\n"
                     "例如：\n名字：小白\n狀態：3")
            user_states[user_id] = {'step': 'awaiting_nutrition_info'}
        elif user_input == "1":
            reply = ("要小心不要讓狗狗吃到這些食物喔！\n"
                     "\n🍎 水果：葡萄、櫻桃、鳳梨、生番茄、酪梨、柑橘類、果核、種子\n"
                     "\n🥕 蔬菜：蔥、韭菜、洋蔥、大蒜、辛香料\n"
                     "\n🚫 其他：蘆薈、巧克力、夏威夷果、野生蘑菇、牛奶、生肉、糕點類\n\n"
                     "幫狗狗準備的食物，請記得要全部煮熟並切成小塊喔~")
        elif user_input == "2":
            reply = "請輸入狗狗的品種名稱（例如：吉娃娃）"
            user_states[user_id] = {'step': 'awaiting_breed_name'}
        elif user_input == "66666":
            reply = "請點選圖文選單中的「紀錄今日攝取」來記錄今日資料，或輸入以下資訊：\n名字：XXX\n卡路里：XX\n水：XX毫升"
            user_states[user_id] = {'step': 'awaiting_daily_record'}
        elif user_input == "77777":
            reply = "請點選圖文選單中的「今日已攝取」來查看今日紀錄，或輸入狗狗的名字："
            user_states[user_id] = {'step': 'awaiting_daily_record_check'}
        elif user_input == "3":
            reply = "請選擇以下方式上傳包裝照片，以計算卡路里和其他營養成分："
            user_states[user_id] = {'step': 'awaiting_package_image'}
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply, quick_reply=quick_reply)]
                )
            )
            app.logger.info("Sent Quick Reply for package image upload")
            return
        elif user_input == "4":
            reply = "請選擇以下方式上傳鮮食照片，以計算卡路里和其他營養成分："
            user_states[user_id] = {'step': 'awaiting_fresh_food_image'}
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply, quick_reply=quick_reply)]
                )
            )
            app.logger.info("Sent Quick Reply for fresh food image upload")
            return
        elif user_input in ["10", "友善餐廳"]:
            reply = "請選擇餐廳查詢方式："
            quick_reply = QuickReply(items=[
                QuickReplyItem(action=MessageAction(label="目前位置", text="目前位置")),
                QuickReplyItem(action=MessageAction(label="輸入地標名稱", text="輸入地標名稱"))
            ])
            user_states[user_id] = {'step': 'awaiting_restaurant_choice'}
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply, quick_reply=quick_reply)]
                )
            )
            app.logger.info("Sent Quick Reply for restaurant choice")
            return
        else:
            reply = welcome_message

        line_bot_api.reply_message_with_http_info(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)]))
        app.logger.info("Replied with initial message")

# 處理 LINE 圖片訊息
@handler.add(MessageEvent, message=ImageMessageContent)
def handle_image_message(event):
    user_id = event.source.user_id
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob_api = MessagingApiBlob(api_client)
        
        # 獲取圖片內容
        message_id = event.message.id
        try:
            response = line_bot_blob_api.get_message_content(message_id=message_id)
            image_content = response
            app.logger.info(f"Successfully retrieved image content for message ID: {message_id}")
        except Exception as e:
            app.logger.error(f"Failed to retrieve image content: {str(e)}")
            reply = "無法獲取圖片，請再試一次。"
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
            )
            return

        # 選項 8：處理包裝照片
        if user_id in user_states and user_states[user_id].get('step') == 'awaiting_package_image':
            try:
                # 使用全局初始化的 vision_client
                nutrition_info = packageOCR.extract_nutrition_info(image_content, vision_client)
                app.logger.info(f"Extracted nutrition info: {nutrition_info}")
                if nutrition_info:
                    user_states[user_id] = {'step': 'awaiting_feeding_weight', 'nutrition_info': nutrition_info}
                    reply = "請問這次餵食的克數？"
                else:
                    reply = "無法從照片中提取營養成分，請再試一次。"
            except Exception as e:
                app.logger.error(f"Error processing package image: {str(e)}")
                reply = "處理圖片時發生錯誤，請再試一次。"
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
            )
            app.logger.info("Processed package image and replied")
        
        # 選項 9：處理鮮食照片
        elif user_id in user_states and user_states[user_id].get('step') == 'awaiting_fresh_food_image':
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_file:
                    temp_file.write(image_content)
                    temp_file_path = temp_file.name
                
                detected_foods = dogdietyolo.detect_food(temp_file_path, yolo_model)
                os.unlink(temp_file_path)
                
                app.logger.info(f"Detected foods (raw): {detected_foods}")
                if detected_foods:
                    # 去重並標準化食材名稱
                    unique_foods = set()
                    for food in detected_foods:
                        if food:  # 過濾空值
                            normalized_food = str(food).strip().title()
                            unique_foods.add(normalized_food)
                    unique_foods = list(unique_foods)
                    app.logger.info(f"Unique foods after normalization: {unique_foods}")
                    
                    # 生成單一回覆訊息，每種食材只顯示一次
                    reply_text = "辨識結果與營養資訊(每100g)：\n" + "=" * 25 + "\n"
                    app.logger.info(f"Initial reply_text: {reply_text}")
                    for food in unique_foods:
                        nutrition = dogdietyolo.NUTRITION_TABLE.get(food, {})
                        food_info = (f"食物: {food}\n"
                                     f"卡路里: {nutrition.get('Calories', 0)} kcal\n"
                                     f"碳水化合物: {nutrition.get('Carbohydrate', 0)} g\n"
                                     f"蛋白質: {nutrition.get('Protein', 0)} g\n"
                                     f"纖維: {nutrition.get('Fiber', 0)} g\n"
                                     f"---------------------------------\n")
                        reply_text += food_info
                        app.logger.info(f"After adding {food}: {reply_text}")
                    
                    # 檢查訊息長度並發送
                    if len(reply_text) > 5000:  # LINE 訊息長度限制
                        reply_text = "辨識結果過多，僅顯示部分資訊：\n" + reply_text[:4900] + "..."
                    app.logger.info(f"Final reply_text: {reply_text}")
                    messages = [TextMessage(text=reply_text.rstrip())]
                else:
                    messages = [TextMessage(text="未辨識到任何食物！")]
                
                app.logger.info(f"Reply messages: {[msg.text for msg in messages]}")
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=messages)
                )
            except Exception as e:
                app.logger.error(f"Error processing fresh food image: {str(e)}")
                reply = "處理圖片時發生錯誤，請再試一次。"
                line_bot_api.reply_message_with_http_info(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=reply)])
                )
            del user_states[user_id]
            app.logger.info("Processed fresh food image and replied")

# 創建圖文選單（使用 message 動作）
def create_rich_menu():
    try:
        # 確保 ACCESS_TOKEN 已正確載入
        if not ACCESS_TOKEN:
            raise ValueError("LINE_CHANNEL_ACCESS_TOKEN not found in environment variables.")

        headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # 定義圖文選單結構，使用 message 動作
        body = {
            "size": {"width": 2500, "height": 1686},
            "selected": True,
            "name": "PetMenu",
            "chatBarText": "選單",
            "areas": [
                # 上排
                {"bounds": {"x": 0, "y": 0, "width": 833, "height": 843}, "action": {"type": "message", "text": "新增寵物檔案", "label": "新增寵物檔案"}},
                {"bounds": {"x": 833, "y": 0, "width": 833, "height": 843}, "action": {"type": "message", "text": "紀錄今日攝取", "label": "紀錄今日攝取"}},
                {"bounds": {"x": 1666, "y": 0, "width": 834, "height": 843}, "action": {"type": "message", "text": "友善餐廳", "label": "友善餐廳"}},
                # 下排
                {"bounds": {"x": 0, "y": 843, "width": 833, "height": 843}, "action": {"type": "message", "text": "狗狗檔案", "label": "狗狗檔案"}},
                {"bounds": {"x": 833, "y": 843, "width": 833, "height":  
843}, "action": {"type": "message", "text": "狗狗檔案", "label": "狗狗檔案"}},
                {"bounds": {"x": 1666, "y": 843, "width": 834, "height": 843}, "action": {"type": "message", "text": "友善餐廳", "label": "友善餐廳"}}
            ]
        }

        # Step 1: 建立 Rich Menu
        response = requests.post("https://api.line.me/v2/bot/richmenu", headers=headers, data=json.dumps(body))
        if response.status_code == 200:
            rich_menu_id = response.json()["richMenuId"]
            app.logger.info(f"✅ Rich Menu 創建成功，ID: {rich_menu_id}")
        else:
            app.logger.error(f"❌ 創建 Rich Menu 失敗：{response.text}")
            raise Exception(f"創建 Rich Menu 失敗：{response.text}")

        # Step 2: 上傳圖片
        headers_image = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "image/jpeg"
        }
        image_path = "richmenu.jpg"
        if not os.path.exists(image_path):
            app.logger.error(f"❌ 圖片檔案 {image_path} 不存在")
            raise FileNotFoundError(f"圖片檔案 {image_path} 不存在")

        with open(image_path, 'rb') as f:
            response = requests.post(
                f"https://api-data.line.me/v2/bot/richmenu/{rich_menu_id}/content",
                headers=headers_image,
                data=f
            )
        if response.status_code == 200:
            app.logger.info("✅ Rich Menu 圖片上傳成功")
        else:
            app.logger.error(f"❌ 上傳 Rich Menu 圖片失敗：{response.text}")
            raise Exception(f"上傳 Rich Menu 圖片失敗：{response.text}")

        # Step 3: 設為預設圖文選單
        headers_set_default = {
            "Authorization": f"Bearer {ACCESS_TOKEN}"
        }
        response = requests.post(
            f"https://api.line.me/v2/bot/user/all/richmenu/{rich_menu_id}",
            headers=headers_set_default
        )
        if response.status_code == 200:
            app.logger.info("✅ Rich Menu 已設為預設")
        else:
            app.logger.error(f"❌ 設為預設 Rich Menu 失敗：{response.text}")
            raise Exception(f"設為預設 Rich Menu 失敗：{response.text}")

    except Exception as e:
        app.logger.error(f"創建圖文選單時發生錯誤：{str(e)}")
        raise

# 建立狗狗檔案
@app.route('/create_dog_profile', methods=['GET', 'POST'])
def create_dog_profile():
    user_id = request.args.get('user_id')
    if not user_id:
        return "缺少 user_id 參數", 400

    # 初始化該使用者的資料庫
    init_db(user_id)

    if request.method == 'POST':
        name = request.form.get('name')
        birthday = request.form.get('birthday')
        weight = request.form.get('weight')
        breed = request.form.get('breed')
        status = request.form.get('status')

        if not all([name, birthday, weight, breed, status]):
            return render_template('create_dog_profile.html', breeds=breeds, statuses=statuses, error="請填寫所有欄位！", user_id=user_id)

        try:
            weight = float(weight)
            datetime.strptime(birthday, '%Y-%m-%d')  # 驗證日期格式
        except ValueError:
            return render_template('create_dog_profile.html', breeds=breeds, statuses=statuses, error="體重必須為數字，生日格式必須為 YYYY-MM-DD！", user_id=user_id)

        db_name = f'dog_database_{user_id}.db'
        conn = sqlite3.connect(db_name)
        c = conn.cursor()
        try:
            c.execute("INSERT INTO dogs (name, birthday, weight, breed, status) VALUES (?, ?, ?, ?, ?)",
                      (name, birthday, weight, breed, status))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template('create_dog_profile.html', breeds=breeds, statuses=statuses, error="此名字已存在，請使用其他名字！", user_id=user_id)
        conn.close()

        status_index = statuses.index(status) + 1
        rer = daily_calories.calculate_RER(weight)
        af_min, af_max = daily_calories.get_AF_for_status(str(status_index))
        der_min = daily_calories.calculate_DER(rer, af_min)
        der_max = daily_calories.calculate_DER(rer, af_max)
        min_water, max_water = daily_calories.calculate_water_intake(weight)

        target_data = {
            'rer': round(rer, 2),
            'der_min': round(der_min, 2),
            'der_max': round(der_max, 2),
            'min_water': round(min_water, 2),
            'max_water': round(max_water, 2)
        }

        return render_template('create_dog_profile.html', breeds=breeds, statuses=statuses, target_data=target_data, user_id=user_id)

    return render_template('create_dog_profile.html', breeds=breeds, statuses=statuses, user_id=user_id)

# 編輯狗狗檔案
@app.route('/edit_dog_profile/<name>', methods=['GET', 'POST'])
def edit_dog_profile(name):
    user_id = request.args.get('user_id')
    if not user_id:
        return "缺少 user_id 參數", 400

    # 獲取狗狗資料
    dog_data = get_dog_data(user_id, name)
    if not dog_data:
        return redirect(url_for('dog_profile', user_id=user_id, error="未找到該狗狗資料！"))

    name, birthday, weight, breed, status, age = dog_data
    dog_data_dict = {
        'name': name,
        'birthday': birthday,
        'weight': weight,
        'breed': breed,
        'status': status,
        'age': age
    }

    if request.method == 'POST':
        new_name = request.form.get('name')
        birthday = request.form.get('birthday')
        weight = request.form.get('weight')
        breed = request.form.get('breed')
        status = request.form.get('status')

        if not all([new_name, birthday, weight, breed, status]):
            return render_template('edit_dog_profile.html', dog_data=dog_data_dict, breeds=breeds, statuses=statuses, error="請填寫所有欄位！", user_id=user_id)

        try:
            weight = float(weight)
            datetime.strptime(birthday, '%Y-%m-%d')  # 驗證日期格式
        except ValueError:
            return render_template('edit_dog_profile.html', dog_data=dog_data_dict, breeds=breeds, statuses=statuses, error="體重必須為數字，生日格式必須為 YYYY-MM-DD！", user_id=user_id)

        # 如果名稱改變，檢查新名稱是否已存在
        if new_name != name:
            db_name = f'dog_database_{user_id}.db'
            conn = sqlite3.connect(db_name)
            c = conn.cursor()
            c.execute("SELECT name FROM dogs WHERE name = ?", (new_name,))
            if c.fetchone():
                conn.close()
                return render_template('edit_dog_profile.html', dog_data=dog_data_dict, breeds=breeds, statuses=statuses, error="此名字已存在，請使用其他名字！", user_id=user_id)
            conn.close()

        # 更新資料庫
        save_dog_data(user_id, new_name, birthday, weight, breed, status)

        # 如果名稱改變，更新 daily_records 表中的名稱
        if new_name != name:
            db_name = f'dog_database_{user_id}.db'
            conn = sqlite3.connect(db_name)
            c = conn.cursor()
            c.execute("UPDATE daily_records SET name = ? WHERE name = ?", (new_name, name))
            conn.commit()
            conn.close()

        # 計算新的目標數據
        status_index = statuses.index(status) + 1
        rer = daily_calories.calculate_RER(weight)
        af_min, af_max = daily_calories.get_AF_for_status(str(status_index))
        der_min = daily_calories.calculate_DER(rer, af_min)
        der_max = daily_calories.calculate_DER(rer, af_max)
        min_water, max_water = daily_calories.calculate_water_intake(weight)

        target_data = {
            'rer': round(rer, 2),
            'der_min': round(der_min, 2),
            'der_max': round(der_max, 2),
            'min_water': round(min_water, 2),
            'max_water': round(max_water, 2)
        }

        # 更新 dog_data_dict 以顯示最新的資料
        dog_data_dict['name'] = new_name
        dog_data_dict['birthday'] = birthday
        dog_data_dict['weight'] = weight
        dog_data_dict['breed'] = breed
        dog_data_dict['status'] = status

        return render_template('edit_dog_profile.html', dog_data=dog_data_dict, breeds=breeds, statuses=statuses, target_data=target_data, user_id=user_id)

    return render_template('edit_dog_profile.html', dog_data=dog_data_dict, breeds=breeds, statuses=statuses, user_id=user_id)

# 狗狗檔案 - 初始頁面
@app.route('/dog_profile')
def dog_profile():
    user_id = request.args.get('user_id')
    if not user_id:
        return "缺少 user_id 參數", 400

    # 初始化該使用者的資料庫
    init_db(user_id)

    dogs = get_all_dogs(user_id)
    error = request.args.get('error')  # 獲取錯誤訊息（如果有）
    return render_template('dog_profile.html', dogs=dogs, error=error, user_id=user_id)

# 狗狗檔案 - 詳細頁面
@app.route('/dog_profile/<name>')
def dog_profile_detail(name):
    user_id = request.args.get('user_id')
    if not user_id:
        return "缺少 user_id 參數", 400

    # 獲取狗狗資料
    dog_data = get_dog_data(user_id, name)
    if not dog_data:
        return render_template('dog_profile.html', error="找不到該狗狗資料", user_id=user_id)

    name, birthday, weight, breed, status, age = dog_data

    # 計算健康資訊
    health_info = get_health_info(breed) if breed else None

    # 計算今日目標
    rer = None
    der_min = None
    der_max = None
    min_water = None
    max_water = None
    if status:
        status_index = statuses.index(status) + 1
        rer = daily_calories.calculate_RER(weight)
        af_min, af_max = daily_calories.get_AF_for_status(str(status_index))
        der_min = int(daily_calories.calculate_DER(rer, af_min))
        der_max = int(daily_calories.calculate_DER(rer, af_max))
        min_water, max_water = daily_calories.calculate_water_intake(weight)
        min_water = int(min_water)
        max_water = int(max_water)

    # 獲取今日已攝取
    record = get_daily_record(user_id, name)
    if record:
        calories, water = record
    else:
        calories, water = 0, 0

    # 計算進度
    calories_progress = (calories / der_max * 100) if der_max else 0
    calories_progress_rounded = round(calories_progress)
    water_progress = (water / max_water * 100) if max_water else 0
    water_progress_rounded = round(water_progress)

    return render_template('dog_profile_detail.html', name=name, birthday=birthday, age=age, weight=weight,
                          breed=breed, status=status, health_info=health_info, rer=rer, der_min=der_min,
                          der_max=der_max, min_water=min_water, max_water=max_water, calories=calories,
                          water=water, calories_progress=calories_progress, calories_progress_rounded=calories_progress_rounded,
                          water_progress=water_progress, water_progress_rounded=water_progress_rounded, user_id=user_id)

# 刪除寵物檔案
@app.route('/delete_dog/<name>', methods=['POST'])
def delete_dog(name):
    user_id = request.form.get('user_id')  # 從表單中獲取 user_id
    if not user_id:
        app.logger.error("缺少 user_id 參數")
        return "缺少 user_id 參數", 400

    db_name = f'dog_database_{user_id}.db'
    conn = sqlite3.connect(db_name)
    c = conn.cursor()
    try:
        # 刪除 dogs 表中的寵物資料
        c.execute("DELETE FROM dogs WHERE name = ?", (name,))
        # 同時刪除 daily_records 表中的相關紀錄
        c.execute("DELETE FROM daily_records WHERE name = ?", (name,))
        conn.commit()
        app.logger.info(f"Successfully deleted dog: {name} for user {user_id}")
    except Exception as e:
        app.logger.error(f"Error deleting dog {name} for user {user_id}: {str(e)}")
        conn.rollback()
        return redirect(url_for('dog_profile', user_id=user_id, error="刪除失敗，請稍後再試！"))
    finally:
        conn.close()
    return redirect(url_for('dog_profile', user_id=user_id))

# 紀錄今日攝取 - 輸入頁面
@app.route('/record_daily_intake', methods=['GET', 'POST'])
def record_daily_intake():
    user_id = request.args.get('user_id')
    if not user_id:
        return "缺少 user_id 參數", 400

    # 初始化該使用者的資料庫
    init_db(user_id)

    dogs = get_all_dogs(user_id)
    if not dogs:
        return redirect(url_for('create_dog_profile', user_id=user_id))

    # 預設選擇第一隻狗（用於 GET 請求時預填表單）
    name = dogs[0][0] if dogs else None

    # 獲取選中狗狗的資料，用於計算目標熱量和水量
    target_calories = 0
    target_water = 0
    consumed_calories = 0
    consumed_water = 0

    if request.method == 'POST':
        name = request.form.get('dog_name')  # 從表單中獲取狗狗名稱
        calories_input = request.form.get('calories', '').strip()
        water_input = request.form.get('water', '').strip()

        # 檢查是否至少填寫了一個欄位
        if not calories_input and not water_input:
            # 重新計算目標值和已攝取值以顯示進度條
            dog_data = get_dog_data(user_id, name)
            if dog_data:
                _, _, weight, _, status, _ = dog_data
                if status:
                    status_index = statuses.index(status) + 1
                    rer = daily_calories.calculate_RER(weight)
                    af_min, af_max = daily_calories.get_AF_for_status(str(status_index))
                    der_min = int(daily_calories.calculate_DER(rer, af_min))
                    der_max = int(daily_calories.calculate_DER(rer, af_max))
                    target_calories = der_max
                    min_water, max_water = daily_calories.calculate_water_intake(weight)
                    target_water = int(max_water)

                # 獲取當前記錄（如果存在）
                current_record = get_daily_record(user_id, name)
                if current_record:
                    consumed_calories, consumed_water = current_record
                else:
                    consumed_calories, consumed_water = 0, 0

            return render_template('daily_intake_progress.html', dogs=dogs, name=name,
                                  error="請至少填寫熱量或水量！", user_id=user_id,
                                  target_calories=target_calories, target_water=target_water,
                                  consumed_calories=consumed_calories, consumed_water=consumed_water)

        try:
            # 獲取當前記錄（如果存在）
            current_record = get_daily_record(user_id, name)
            current_calories, current_water = current_record if current_record else (0, 0)

            # 處理輸入值，允許空值
            calories = int(float(calories_input)) if calories_input else 0
            water = int(float(water_input)) if water_input else 0

            # 累加熱量和水量
            total_calories = current_calories + calories
            total_water = current_water + water

            # 儲存累加後的資料
            save_daily_record(user_id, name, total_calories, total_water)

            # 提交後重定向到 dog_profile_detail，傳遞狗狗名稱和 user_id
            return redirect(url_for('dog_profile_detail', name=name, user_id=user_id))
        except ValueError:
            # 重新計算目標值和已攝取值以顯示進度條
            dog_data = get_dog_data(user_id, name)
            if dog_data:
                _, _, weight, _, status, _ = dog_data
                if status:
                    status_index = statuses.index(status) + 1
                    rer = daily_calories.calculate_RER(weight)
                    af_min, af_max = daily_calories.get_AF_for_status(str(status_index))
                    der_min = int(daily_calories.calculate_DER(rer, af_min))
                    der_max = int(daily_calories.calculate_DER(rer, af_max))
                    target_calories = der_max
                    min_water, max_water = daily_calories.calculate_water_intake(weight)
                    target_water = int(max_water)

                # 獲取當前記錄（如果存在）
                current_record = get_daily_record(user_id, name)
                if current_record:
                    consumed_calories, consumed_water = current_record
                else:
                    consumed_calories, consumed_water = 0, 0

            return render_template('daily_intake_progress.html', dogs=dogs, name=name,
                                  error="熱量和水量必須為數字！", user_id=user_id,
                                  target_calories=target_calories, target_water=target_water,
                                  consumed_calories=consumed_calories, consumed_water=consumed_water)

    # GET 請求：顯示表單時計算目標值和已攝取值
    dog_data = get_dog_data(user_id, name)
    if dog_data:
        _, _, weight, _, status, _ = dog_data
        if status:
            status_index = statuses.index(status) + 1
            rer = daily_calories.calculate_RER(weight)
            af_min, af_max = daily_calories.get_AF_for_status(str(status_index))
            der_min = int(daily_calories.calculate_DER(rer, af_min))
            der_max = int(daily_calories.calculate_DER(rer, af_max))
            target_calories = der_max
            min_water, max_water = daily_calories.calculate_water_intake(weight)
            target_water = int(max_water)

        # 獲取當前記錄（如果存在）
        current_record = get_daily_record(user_id, name)
        if current_record:
            consumed_calories, consumed_water = current_record
        else:
            consumed_calories, consumed_water = 0, 0

    return render_template('daily_intake_progress.html', dogs=dogs, name=name, user_id=user_id,
                          target_calories=target_calories, target_water=target_water,
                          consumed_calories=consumed_calories, consumed_water=consumed_water)

if __name__ == "__main__":
    try:
        create_rich_menu()
    except Exception as e:
        app.logger.error(f"Failed to initialize rich menu: {str(e)}")
        raise
    app.run(host='0.0.0.0', port=5000, debug=True)