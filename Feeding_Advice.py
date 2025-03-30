import requests
from bs4 import BeautifulSoup
from google.cloud import translate_v2 as translate
from dotenv import load_dotenv
import os
import re


# 中文轉英文的字典
def translate_breed_to_english(breed_input):
    breed_dict = {
        "吉娃娃": "Chihuahua",
        "博美犬": "Pomeranian",
        "約克夏": "Yorkshire Terrier",
        "西施犬": "Shih Tzu",
        "馬爾濟斯": "Maltese",
        "臘腸犬": "Dachshund",
        "玩具貴賓犬": "Toy Poodle",
        "巨型貴賓犬": "Standard Poodle",
        "柴犬": "Shiba Inu",
        "雪納瑞": "Miniature Schnauzer",
        "拉布拉多": "Labrador Retriever",
        "黃金獵犬": "Golden Retriever",
        "法國鬥牛犬": "French Bulldog",
        "比熊犬": "Bichon Frise",
        "西高地白梗": "West Highland White Terrier",
        "柯基": "Pembroke Welsh Corgi",
        "哈士奇": "Siberian Husky",
        "薩摩耶": "Samoyed",
        "杜賓犬": "Doberman Pinscher",
        "大丹犬": "Great Dane",
        "羅威納": "Rottweiler",
        "鬆獅犬": "Chow Chow",
        "米格魯": "Beagle",
        "邊境牧羊犬": "Border Collie",
    }
    
    breed_in_english = breed_dict.get(breed_input)
    return breed_in_english if breed_in_english else "未找到對應的英文品種名稱"


# 爬取品種資訊
def fetch_breed_info(breed_input):
    breed_in_english = translate_breed_to_english(breed_input)
    
    if breed_in_english == "未找到對應的英文品種名稱":
        print("未找到該品種的資訊，請確認品種名稱是否正確。")
        return None
    
    breed_in_english_url = breed_in_english.lower().replace(" ", "-")
    url = f"https://www.petmd.com/dog/breeds/{breed_in_english_url}"
    print(f"發送請求到: {url}")

    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            print(f"請求成功，狀態碼: {response.status_code}")
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup
        else:
            print(f"請求失敗，狀態碼: {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print("請求超時！")
        return None
    except requests.exceptions.RequestException as e:
        print(f"請求錯誤：{e}")
        return None


# 翻譯文本為繁體中文
def translate_text_to_chinese(text):
    if text:
        result = translate_client.translate(text, target_language='zh-TW')
        return result['translatedText']
    return text


# 處理 "What To Feed" 的資訊並翻譯
def get_what_to_feed_info(soup):
    if not soup:
        print("沒有有效的頁面內容，無法繼續處理。")
        return None

    # 使用正則表達式進行匹配
    whattofeed_title = soup.find('h2', string=re.compile(r'What\s*To\s*Feed', re.IGNORECASE))
    
    if whattofeed_title:
        #print("\n標題:", translate_text_to_chinese(whattofeed_title.get_text(strip=False)))

        paragraphs = []
        current_tag = whattofeed_title.find_next_sibling()

        while current_tag and current_tag.name != 'h3':
            if current_tag.name == 'p':
                paragraph_text = current_tag.get_text(strip=False).replace('\n', ' ').strip()
                paragraph_text = paragraph_text.replace('\u00A0', ' ')
                paragraphs.append(translate_text_to_chinese(paragraph_text))
            elif current_tag.name == 'ul':
                list_items = [translate_text_to_chinese(li.get_text(strip=True).replace('\u00A0', ' ')) for li in current_tag.find_all('li')]
                paragraphs.extend(list_items)
            current_tag = current_tag.find_next_sibling()

        if paragraphs:
            for paragraph in paragraphs:
                print(paragraph)
        else:
            print("未提取到任何段落內容。")
    else:
        print("未找到包含 'What To Feed' 的 <h2> 標籤")


# 處理 "How To Feed" 的資訊並翻譯
def get_how_to_feed_info(soup):
    if not soup:
        print("沒有有效的頁面內容，無法繼續處理。")
        return None

    h3_title = soup.find('h3', string=re.compile(r'How\s*To\s*Feed', re.IGNORECASE))
    
    if h3_title:
        #print("\n標題:", translate_text_to_chinese(h3_title.get_text(strip=False)))
        current_tag = h3_title.find_next_sibling()

        while current_tag:
            if current_tag.name == 'p':
                paragraph_text = current_tag.get_text(strip=False).replace('\n', ' ').strip()
                paragraph_text = paragraph_text.replace('\u00A0', ' ')
                print(translate_text_to_chinese(paragraph_text))
            elif current_tag.name == 'ul':
                list_items = [translate_text_to_chinese(li.get_text(strip=True).replace('\u00A0', ' ')) for li in current_tag.find_all('li')]
                for item in list_items:
                    print(item)
            elif current_tag.name == 'h3':
                break
            current_tag = current_tag.find_next_sibling()
    else:
        print("未找到 'How To Feed' 相關的 <h3> 標籤，繼續處理後續內容。")


# 處理 "Nutritional Tips" 的資訊並翻譯
def get_nutritional_tips_info(soup):
    if not soup:
        print("沒有有效的頁面內容，無法繼續處理。")
        return None

    h3_title = soup.find('h3', string=lambda x: x and 'Nutritional Tips' in x)

    if h3_title:
        #print("\n標題:", translate_text_to_chinese(h3_title.get_text(strip=False)))

        current_tag = h3_title.find_next_sibling()

        while current_tag:
            if current_tag.name == 'p':
                paragraph_text = current_tag.get_text(strip=False).replace('\n', ' ').strip()
                paragraph_text = paragraph_text.replace('\u00A0', ' ')
                print(translate_text_to_chinese(paragraph_text))
            elif current_tag.name == 'ul':
                list_items = [translate_text_to_chinese(li.get_text(strip=True).replace('\u00A0', ' ')) for li in current_tag.find_all('li')]
                for item in list_items:
                    print(item)
            elif current_tag.name == 'h3':
                break
            current_tag = current_tag.find_next_sibling()
    else:
        print("未找到 'Nutritional Tips' 相關的標籤")



# 主程序
def main():
    while True:
        breed_input = input("請輸入品種名稱：")
        soup = fetch_breed_info(breed_input)
        
        if soup:
            get_what_to_feed_info(soup)
            get_how_to_feed_info(soup)
            get_nutritional_tips_info(soup)
            break
        else:
            print("請重新輸入正確的品種名稱。\n")



if __name__ == "__main__":
    # 加載環境變數
    load_dotenv('information.env')

    # Google 翻譯 API 客戶端
    translate_client = translate.Client.from_service_account_json(os.getenv('GOOGLE_Translation_API_KEY'))

    main()

