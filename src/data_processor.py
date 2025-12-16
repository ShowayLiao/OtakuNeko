# src/data_processor.py
import json
import os
from datetime import datetime, timedelta
from src.BgmServe import bgm_service

# 定义路径
BASE_DIR = "data"
SOURCE_FILE = os.path.join(BASE_DIR, "bangumi_full_records.json")
EXPORT_DIR = os.path.join(BASE_DIR, "datasets")

def load_json_file(filepath):
    """通用工具：读取 JSON"""
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def export_categorized_datasets():
    """
    📂 数据分包导出核心逻辑 (Refactored)
    利用 fetch_dataset 获取全量数据，然后进行内存分包
    """

    # 1. 获取全量数据 (利用 fetch_dataset 的兜底逻辑：有文件读文件，没文件读库)
    # 这里不传 status_filter，意为获取所有数据
    records = fetch_dataset(file_path=SOURCE_FILE)
    
    if not records:
        return "⚠️ 主数据库为空或文件不存在，无法导出。"

    # 2. 初始化容器
    categories = {
        "watched": [],  # 看过
        "wish": [],     # 想看
        "doing": [],    # 在看 + 搁置
        "dropped": []   # 抛弃
    }

    # 3. 分类逻辑 (保持原有逻辑)
    # 也可以多次调用 fetch_dataset(status_filter=...)，但那样会读多次文件/库，
    # 内存分包效率更高。
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

    # 4. 写入文件 (保持原有 I/O 逻辑)
    if not os.path.exists(EXPORT_DIR):
        os.makedirs(EXPORT_DIR)

    results = []
    count_map = {}
    
    for key, data_list in categories.items():
        file_name = f"dataset_{key}.json"
        file_path = os.path.join(EXPORT_DIR, file_name)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data_list, f, ensure_ascii=False, indent=2)
            
        count = len(data_list)
        count_map[key] = count
        results.append(f"{key}: {count}")

    return f"✅ 导出完成! 路径: {EXPORT_DIR}\n📊 统计: " + " | ".join(results)

def extract_recent_watched(days=730):
    """
    📅 提取最近 X 天的观看记录 (Refactored)
    利用 fetch_dataset 的时间过滤功能，大幅简化代码
    """
    
    source_path = "data/datasets/dataset_watched.json"
    target_path = f"data/datasets/dataset_recent_{days}.json"
    
    # 🟢 1. 核心调用：直接利用基类方法进行 读取 + 状态过滤 + 时间过滤 + 排序
    # 注意：这里我们传入 days 参数，fetch_dataset 会自动处理日期计算和筛选
    try:
        filtered_data = fetch_dataset(
            file_path=source_path, 
            status_filter='watched', 
            days=days
        )
    except Exception as e:
        return f"❌ 提取失败: {e}"

    if not filtered_data and not os.path.exists(source_path):
            return "⚠️ 未找到已看列表或数据为空，跳过最近记录提取。"

    # 🟢 2. 格式化逻辑 (Full vs Light)
    # fetch_dataset 返回的是全量字段，我们需要根据 days 决定保留哪些字段
    recent_items = []
    is_full_mode = (days == 365)

    for item in filtered_data:
        if is_full_mode:
            # 全量模式：保留生成海报/报告所需的所有字段
            recent_items.append({
                "id": item.get('id'),
                "title": item.get('title'),
                "score": item.get('score', 'N/A'),
                "tags": item.get('tags', []),
                "image": item.get('image', ''),
                "comment": item.get('comment', ''),
                "updated_at": item.get('updated_at', ''),
                "summary": item.get('summary', '')[:100],
                "month": item.get('month', 0),
                "year": item.get('year', 0),
                "cv": item.get('cv', []),
            })
        else:
            # 轻量模式：仅保留 Prompt 必须的字段
            recent_items.append({
                "title": item.get('title'),
                "tags": item.get('tags', [])[:2]
            })

    # 3. 写入文件
    try:
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(recent_items, f, ensure_ascii=False, indent=2)
            
        mode_str = "全量信息" if is_full_mode else "轻量信息"
        return f"✅ 已提取近 {days} 天记录 ({mode_str})，共 {len(recent_items)} 条。"
        
    except Exception as e:
        return f"❌ 写入失败: {e}"
    

def fetch_dataset(file_path: str = None, status_filter: str = None, limit: int = 0, days: int = 0) -> list:
    """
    📂 通用数据加载 (基类公共方法 - 增强版)
    """
    from datetime import datetime, timedelta

    data = []

    # --- 1. 优先读取文件 ---
    if file_path:
        # 假设有个 load_json_file 方法在上下文里
        # data = self.load_json_file(file_path) 
        # 这里为了演示方便，假设你是在类内部，或者引入了那个函数
        pass 

    # --- 2. 数据库兜底逻辑 ---
    if not data and status_filter:
        try:
            # A. 加载全量
            full_records = bgm_service.load_local_records()
            
            # B. 状态过滤
            filtered_records = [x for x in full_records if x.get('status') == status_filter]
            
            # C. 时间范围过滤 (修复版 🟢)
            if days > 0:
                now = datetime.now()
                cutoff_date = now - timedelta(days=days)
                time_filtered = []
                
                for item in filtered_records:
                    updated_at_str = item.get('updated_at', '')
                    if not updated_at_str: continue
                    
                    try:
                        # 1. 解析完整 ISO 格式 (包含时区 +08:00)
                        # e.g., "2025-12-12T01:31:25+08:00"
                        item_dt = datetime.fromisoformat(updated_at_str)
                        
                        # 2. 关键修正：移除时区信息，使其变成 Naive 时间
                        # 这样才能和 datetime.now() (Naive) 进行无报错比较
                        item_dt_naive = item_dt.replace(tzinfo=None)
                        
                        # 3. 比较
                        if item_dt_naive >= cutoff_date:
                            time_filtered.append(item)
                    except ValueError:
                        # 遇到无法解析的格式 (如空字符串或非ISO格式) 跳过
                        continue
                
                filtered_records = time_filtered

            # D. 排序 (始终按时间倒序)
            filtered_records.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
            
            # E. 数量截取
            if limit > 0:
                data = filtered_records[:limit]
            else:
                data = filtered_records
                
        except Exception as e:
            print(f"❌ [BaseAgent] 读取本地数据库失败: {e}")

    return data
    
def extract_data(items: list, *fields) -> str:
    """
    🧬 动态提取数据 (支持 *args 传入任意多个字段)
    
    :param items: 数据列表
    :param fields: 需要提取的字段名 (字符串)。
                    例如: "title", "director", "cv"
    :return: JSON 字符串列表
    """
    import json

    formatted_list = []
    if not items:
        return json.dumps([], ensure_ascii=False)

    for item in items:
        parts = []
        
        # 🔄 遍历用户传入的每一个字段名 (*args)
        for field in fields:
            # 1. 安全获取值
            val = item.get(field)
            
            # 2. 空值跳过 (根据需求，也可以填 "无")
            if not val and val != 0: 
                continue
            
            # 3. 类型自动处理
            if isinstance(val, list):
                #如果是列表 (如 tags: []), 转成字符串 "[A,B]"
                val_str = f"[{','.join(str(x) for x in val)}]"
            else:
                # 如果是普通值 (如 year: 2025, cv: "xxx"), 直接转字符串
                val_str = str(val).strip()
            
            # 4. 存入片段
            # 这里做了一个小优化：如果提取的不是标题，加上 Key 前缀方便 AI 理解
            # (你可以根据喜好决定要不要加这个 field+":")
            if field == 'title':
                parts.append(f"《{val_str}》")
            else:
                # 例如: "director:今井友紀子"
                parts.append(f"{field}:{val_str}")
        
        # 5. 将该条目的所有字段用空格或 | 拼起来
        if parts:
            formatted_list.append(" ".join(parts))

    return json.dumps(formatted_list, ensure_ascii=False)

# 如果直接运行这个文件，也可以执行导出
if __name__ == "__main__":
    print(export_categorized_datasets())