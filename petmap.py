import os
import requests
import json
import geocoder
from dotenv import load_dotenv

def get_place_detail_fields():
    return [
        'places.location',
        'places.displayName',
        'places.formattedAddress',
        'places.reviews',
        'places.rating',
        'places.allowsDogs'
    ]

def search_place_by_name(api_key, text_query, fields=get_place_detail_fields()):
    URL = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join(fields)
    }
    payload = {"textQuery": text_query}
    response = requests.post(URL, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        results = response.json().get("places", [])
        return results if results else []
    return []

def search_nearby_places(api_key, lat, lon, fields=get_place_detail_fields(), radius=1000, place_type=['restaurant'], max_count=20):
    URL = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": ",".join(fields)
    }
    payload = {
        "includedTypes": place_type,
        "maxResultCount": max_count,
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lon},
                "radius": radius
            }
        }
    }
    response = requests.post(URL, headers=headers, data=json.dumps(payload))
    if response.status_code == 200:
        return response.json().get("places", [])
    return []

def get_location(api_key, choice, place_name=None):
    if choice == '1':
        g = geocoder.ip('me')
        LAT, LON = g.latlng
        if LAT is None or LON is None:
            return None, None, "無法獲取當前位置，請確認網路或位置服務。"
        return LAT, LON, f"目前位置：經度 {LAT}, 緯度 {LON}"
    elif choice == '2':
        # 将输入地标名称的逻辑移到函数内部
        if place_name is None:  # 如果外部未提供 place_name，则提示用户输入
            place_name = input("請輸入地標名稱: ").strip()
        places = search_place_by_name(api_key, place_name)
        if not places:
            return None, None, f"未找到 '{place_name}' 的相關資訊。"
        location = places[0]['location']
        LAT, LON = location['latitude'], location['longitude']
        return LAT, LON, f"{place_name} 的經度: {LAT}, 緯度: {LON}"
    return None, None, "無效選擇或缺少地標名稱。"

if __name__ == "__main__":
    load_dotenv('information.env')
    API_KEY = os.getenv("GOOGLE_MAP_API_KEY")

    choice = input("請選擇搜尋方式(輸入1或2):\n1. 目前位置\n2. 輸入地標名稱\n選擇 (1/2): ").strip()

    # 直接调用 get_location，不需要额外的 if-else
    LAT, LON, message = get_location(API_KEY, choice)

    print(message)  # 打印消息以确认位置信息

    if LAT is not None and LON is not None:  # 检查是否成功获取位置
        places = search_nearby_places(API_KEY, LAT, LON, max_count=20, place_type=['dog_cafe', 'cat_cafe', 'restaurant'])
        for place in places:
            is_allow_dogs = place.get('allowsDogs', False)
            if is_allow_dogs:
                print(f"🍴 餐廳: {place.get('displayName', {}).get('text', '未知')}")
                print(f"⭐ 評分: {place.get('rating', '無評分')}")
                print(f"📍 地址: {place.get('formattedAddress', '地址未知')}")
                print()
    else:
        print("無法繼續搜尋，因為未獲取到有效位置。")