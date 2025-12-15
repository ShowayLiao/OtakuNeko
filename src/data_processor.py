# src/data_processor.py
import json
import os
from datetime import datetime, timedelta

# 定义路径
BASE_DIR = "data"
SOURCE_FILE = os.path.join(BASE_DIR, "bangumi_full_records.json")
EXPORT_DIR = os.path.join(BASE_DIR, "datasets")

def load_source_data():
    """读取主数据文件"""
    if not os.path.exists(SOURCE_FILE):
        return []
    try:
        with open(SOURCE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return []

def export_categorized_datasets():
    """
    📂 数据分包导出核心逻辑
    将 bangumi_full_records.json 按照 status 拆分成多个独立文件
    """
    records = load_source_data()
    if not records:
        return "⚠️ 主数据库为空或文件不存在，无法导出。"

    # 1. 初始化容器
    categories = {
        "watched": [],  # 看过
        "wish": [],     # 想看 (适合做新番推荐)
        "doing": [],    # 在看 + 搁置 (适合做排期)
        "dropped": []   # 抛弃 (适合做负面样本)
    }

    # 2. 分类逻辑
    count_map = {k: 0 for k in categories.keys()}
    
    for r in records:
        status = r.get('status')
        
        if status == 'watched':
            categories['watched'].append(r)
        elif status == 'wish':
            categories['wish'].append(r)
        elif status in ['watching', 'on_hold']:
            categories['doing'].append(r)
        elif status == 'dropped':
            categories['dropped'].append(r)

    # 3. 写入文件
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    results = []
    for key, data_list in categories.items():
        file_name = f"dataset_{key}.json"
        file_path = os.path.join(EXPORT_DIR, file_name)
        
        # 写入
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
            
        count = len(data_list)
        count_map[key] = count
        results.append(f"{key}: {count}")

    return f"✅ 导出完成! 路径: {EXPORT_DIR}\n📊 统计: " + " | ".join(results)

def extract_recent_watched(days=730):
    """
    📅 提取最近 X 天的观看记录
    策略：如果 days==365 (年度总结模式)，则提取全量信息(含图片)；否则只提取标题(省Token)。
    """
    # 年度总结固定读取 dataset_recent.json
    source_path = "data/datasets/dataset_watched.json"
    target_path = f"data/datasets/dataset_recent_{days}.json" 
    
    if not os.path.exists(source_path):
        return "⚠️ 未找到已看列表，跳过最近记录提取。"
    
    try:
        with open(source_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        recent_items = []
        now = datetime.now()
        cutoff_date = now - timedelta(days=days)
        
        # 🟢 核心逻辑：是否提取全量信息
        is_full_mode = (days == 365)
        
        for item in data:
            updated_at_str = item.get('updated_at', '')
            if not updated_at_str: continue
            
            try:
                date_str = updated_at_str[:10]
                item_date = datetime.fromisoformat(date_str)
                
                if item_date >= cutoff_date:
                    if is_full_mode:
                        # 🟢 全量模式 (年度总结用)：保留图片、ID、评分
                        recent_items.append({
                            "id": item.get('id'),
                            "title": item.get('title'),
                            "score": item.get('score', 'N/A'),
                            "tags": item.get('tags', []),
                            "image": item.get('image', ''), # 关键：图片链接
                            "comment": item.get('comment', ''),
                            "updated_at": item.get('updated_at', ''),
                            "summary": item.get('summary', '')[:100]
                        })
                    else:
                        # 🟡 轻量模式 (平时 Prompt 用)：只存标题和标签，极度节省 Token
                        recent_items.append({
                            "title": item['title'],
                            "tags": item.get('tags', [])[:2]
                        })
            except:
                continue 
                
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(recent_items, f, ensure_ascii=False, indent=2)
            
        mode_str = "全量信息" if is_full_mode else "轻量信息"
        return f"✅ 已提取近 {days} 天记录 ({mode_str})，共 {len(recent_items)} 条。"
        
    except Exception as e:
        return f"❌ 提取失败: {e}"

# 如果直接运行这个文件，也可以执行导出
if __name__ == "__main__":
    print(export_categorized_datasets())