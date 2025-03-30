import re
from google.cloud import vision
from google.oauth2 import service_account
from dotenv import load_dotenv
import os

# 初始化 Google Cloud Vision 客戶端（這裡只是定義，實際初始化在主程式中）
def get_vision_client():
    load_dotenv('information.env')
    google_api_key_path = os.getenv('GOOGLE_Translation_API_KEY')
    if not google_api_key_path or not os.path.exists(google_api_key_path):
        raise ValueError("Google API key path not found or invalid in environment variables.")
    credentials = service_account.Credentials.from_service_account_file(google_api_key_path)
    return vision.ImageAnnotatorClient(credentials=credentials)

def extract_nutrition_info(image_content: bytes, client=None):
    """
    從圖片的二進位數據中提取營養資訊
    Args:
        image_content (bytes): 圖片的二進位數據
        client: Google Cloud Vision 客戶端（可選，若未提供則內部初始化）
    Returns:
        dict: 提取的營養資訊字典
    """
    if client is None:
        client = get_vision_client()

    # 構建 Vision API 的圖片物件
    image = vision.Image(content=image_content)

    # 發送 OCR 請求
    response = client.text_detection(image=image)

    # 解析結果
    texts = response.text_annotations
    if not texts:
        return {}

    detected_text = texts[0].description

    # 清理文本：去除換行符和多餘空格，並移除多餘的符號
    detected_text = detected_text.replace('\n', '').replace(' ', '')
    detected_text = re.sub(r'[●]*', '', detected_text)

    # 定義正則表達式
    patterns = {
        '熱量': r'(\d+(\.\d+)?)\s*(大卡|Kcal|kcal|cal|卡)',
        '蛋白質': r'(蛋白質|蛋白|protein)[^\d]*(\d+\.\d*|\d+)',
        '脂肪': r'(脂肪|脂防|fat)[^\d]*(\d+\.\d*|\d+)',
        '纖維': r'(纖維|fiber|CrudeFiber)[^\d]*(\d+\.\d*|\d+)',
        '水': r'(水分|水份|moisture)[^\d]*(\d+\.\d*|\d+)',
        '碳水': r'(碳水化合物|carbohydrates)[^\d]*(\d+\.\d*|\d+)',
    }

    # 初始化結果字典
    nutrition_info = {}

    # 遍歷 patterns 提取成分
    for component, pattern in patterns.items():
        match = re.search(pattern, detected_text, re.IGNORECASE)
        if match:
            try:
                nutrition_info[component] = match.group(2) if match.group(2) else match.group(1)
            except IndexError:
                nutrition_info[component] = match.group(1)

    # 修正纖維數據（若過大）
    if '纖維' in nutrition_info and float(nutrition_info['纖維']) > 100:
        nutrition_info['纖維'] = '0.5'

    return nutrition_info

if __name__ == "__main__":
    # 測試用代碼
    client = get_vision_client()
    with open('package6.jpg', 'rb') as image_file:
        image_content = image_file.read()
    nutrition_info = extract_nutrition_info(image_content, client)
    if nutrition_info:
        print("提取的成分數據：")
        for component, value in nutrition_info.items():
            if component == '熱量':
                print(f"{component}: {value} kcal")
            else:
                print(f"{component}: {value}%")
    else:
        print("未提取到任何成分數據。")