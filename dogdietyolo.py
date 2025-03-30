import cv2
import numpy as np
import os
from ultralytics import YOLO
from tkinter import Tk, filedialog

# 定義食物營養表
NUTRITION_TABLE = {
    "Chicken Breast": {"Calories": 115, "Carbohydrate": 0, "Protein": 24, "Fiber": 0},
    "Beef": {"Calories": 288, "Carbohydrate": 0, "Protein": 26.3, "Fiber": 0},
    "Salmon": {"Calories": 139, "Carbohydrate": 0, "Protein": 24.3, "Fiber": 0},
    "Egg": {"Calories": 140, "Carbohydrate": 1.7, "Protein": 13, "Fiber": 0},
    "Sweet Potato": {"Calories": 110, "Carbohydrate": 27.8, "Protein": 1.6, "Fiber": 2.5},
    "Brown Rice": {"Calories": 354, "Carbohydrate": 75.1, "Protein": 7.5, "Fiber": 4.9},
    "Pumpkin": {"Calories": 74, "Carbohydrate": 17.3, "Protein": 1.9, "Fiber": 2.5},
    "Carrot": {"Calories": 41, "Carbohydrate": 9.6, "Protein": 0.9, "Fiber": 2.8},
    "Broccoli": {"Calories": 25, "Carbohydrate": 4.8, "Protein": 2.2, "Fiber": 2.3},
    "Tomato": {"Calories": 18, "Carbohydrate": 4, "Protein": 0.8, "Fiber": 1.1},
    "Blueberry": {"Calories": 57, "Carbohydrate": 14.5, "Protein": 0.7, "Fiber": 2.4},
}

def select_image():
    """使用 Tkinter 開啟檔案選擇對話框，讓使用者選擇圖片"""
    root = Tk()
    file_path = filedialog.askopenfilename(
        title="選擇一張圖片",
        filetypes=[("Image files", "*.jpg *.jpeg *.png *.bmp")]
    )
    return file_path if file_path else None

def load_yolo_model(model_path):
    """載入 YOLO 模型"""
    if not model_path or not isinstance(model_path, str):
        print("模型路徑無效，請提供正確的路徑！")
        return None
    
    if not os.path.exists(model_path):
        print(f"模型檔案 {model_path} 不存在，請確認路徑！")
        return None
    
    model = YOLO(model_path)
    return model

def detect_food(image_path, model):
    """使用 YOLO 模型進行食物辨識"""
    if not image_path or not os.path.exists(image_path):
        print("圖片路徑無效或檔案不存在，請確認！")
        return None

    # 讀取圖片
    img = cv2.imread(image_path)
    if img is None:
        print("無法讀取圖片，請確認圖片格式或路徑是否正確！")
        return None

    # 使用 YOLO 模型進行預測
    results = model.predict(source=img, conf=0.25)

    # 提取辨識結果
    detected_foods = []
    print("YOLO 辨識結果：")
    for result in results:
        for box in result.boxes.data:
            class_id = int(box[5])  # 類別 ID
            label = model.names[class_id]  # 原始標籤
            print(f" - 原始標籤: {label}")
            # 將標籤轉換為與 NUTRITION_TABLE 一致的格式（首字母大寫）
            normalized_label = label.title()
            if normalized_label in NUTRITION_TABLE:
                detected_foods.append(normalized_label)
                print(f" - 匹配成功: {normalized_label}")
            else:
                print(f" - 未找到營養資訊: {normalized_label}")

    return detected_foods

def display_nutrition(detected_foods):
    """顯示辨識出的食物的營養資訊"""
    if not detected_foods:
        print("未辨識到任何食物！")
        return

    print("\n辨識結果與營養資訊：")
    print("-" * 50)
    for food in set(detected_foods):  # 使用 set 避免重複顯示
        nutrition = NUTRITION_TABLE[food]
        print(f"食物: {food}")
        print(f"卡路里: {nutrition['Calories']} kcal")
        print(f"碳水化合物: {nutrition['Carbohydrate']} g")
        print(f"蛋白質: {nutrition['Protein']} g")
        print(f"纖維: {nutrition['Fiber']} g")
        print("-" * 50)

def main():
    # 載入 YOLO 模型（請替換為你的模型路徑）
    model_path = "best.pt"  # 替換為你的 YOLO 模型路徑
    model = load_yolo_model(model_path)
    if model is None:
        return

    # 打印模型的類別名稱，方便檢查
    print("模型支持的類別名稱：", model.names)

    while True:
        print("\n請選擇操作：")
        print("1. 上傳圖片進行食物辨識")
        print("2. 退出程式")
        choice = input("輸入選項 (1 或 2)：").strip()

        if choice == "2":
            print("程式結束！")
            break

        if choice != "1":
            print("無效選項，請重新輸入！")
            continue

        # 選擇圖片
        image_path = select_image()
        if not image_path:
            print("未選擇圖片，請重新操作！")
            continue

        # 進行食物辨識
        detected_foods = detect_food(image_path, model)
        if detected_foods is None:
            continue

        # 顯示營養資訊
        display_nutrition(detected_foods)

if __name__ == "__main__":
    main()