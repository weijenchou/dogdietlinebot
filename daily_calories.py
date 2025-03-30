# daily_calories.py

def calculate_RER(weight):
    """
    計算基礎能量需求 (Resting Energy Requirement, RER)
    參數:
        weight (float): 狗狗的體重（公斤）
    返回:
        float: RER 值（單位：kcal）
    """
    return 70 * (weight ** 0.75)

def calculate_DER(rer, af):
    """
    計算日常能量需求 (Daily Energy Requirement, DER)
    參數:
        rer (float): 基礎能量需求（kcal）
        af (float): 活動因子
    返回:
        float: DER 值（單位：kcal）
    """
    return rer * af

def calculate_water_intake(weight):
    """
    計算每日喝水量
    參數:
        weight (float): 狗狗的體重（公斤）
    返回:
        tuple: (min_water, max_water) 每日喝水量範圍（單位：ml）
    """
    min_water = weight * 50  # 每公斤體重 50ml
    max_water = weight * 60  # 每公斤體重 60ml
    return min_water, max_water

def get_AF_for_status(status):
    """
    根據狗狗的狀態返回活動因子 (Activity Factor) 的最小值和最大值
    參數:
        status (str): 狀態編號（1-13）
    返回:
        tuple: (af_min, af_max)
    """
    af_dict = {
        "1": (2.5, 3.0),  # 正在發育的幼犬(4個月以下)
        "2": (2.0, 2.5),  # 正在發育的幼犬(4個月-1歲)
        "3": (1.4, 1.6),  # 結紮成年犬(1-7歲)
        "4": (1.6, 1.8),  # 未結紮成年犬(1-7歲)
        "5": (1.2, 1.4),  # 輕度減肥成年犬
        "6": (1.0, 1.2),  # 重度減肥成年犬
        "7": (1.6, 2.0),  # 過瘦成年犬
        "8": (1.2, 1.4),  # 輕度活動量
        "9": (2.0, 2.5),  # 劇烈活動量
        "10": (1.2, 1.4), # 高齡犬
        "11": (1.8, 2.0), # 懷孕中的狗媽媽
        "12": (2.2, 2.5), # 哺乳中的狗媽媽
        "13": (1.0, 1.5)  # 生病成年犬
    }
    return af_dict.get(status, (1.6, 1.8))  # 如果狀態編號無效，返回默認值