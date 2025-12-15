# src/bgm_sync.py
import requests
import time
import json
import os
import traceback
from dotenv import load_dotenv
import requests
import urllib.parse

load_dotenv()

# --- 配置 ---
ACCESS_TOKEN = os.getenv("BGM_ACCESS_TOKEN")
USERNAME = os.getenv("BGM_USERNAME")
DATA_DIR = "data"
DATA_FILE = "bangumi_full_records.json"
DATA_PATH = os.path.join(DATA_DIR, DATA_FILE)

HEADERS = {
    "User-Agent": "OtakuMate/1.0 (local_learning_project)", 
    "Authorization": f"Bearer {ACCESS_TOKEN}"
}

STATUS_MAP = { 1: "wish", 2: "watched", 3: "watching", 4: "on_hold", 5: "dropped" }

def load_local_records():
    if not os.path.exists(DATA_PATH): return []
    try:
        with open(DATA_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except: return []

def save_records(records):
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

def parse_infobox_info(infobox):
    """提取监督、脚本、制作公司"""
    if not infobox or not isinstance(infobox, list):
        return {}
    
    meta = { "director": [], "script": [], "studio": [] }
    key_map = {
        "导演": "director", "监督": "director", "Director": "director",
        "脚本": "script", "系列构成": "script", "Script": "script",
        "动画制作": "studio", "制作公司": "studio", "Studio": "studio"
    }

    for item in infobox:
        key = item.get('key')
        if key in key_map:
            target = key_map[key]
            value = item.get('value')
            if isinstance(value, str): meta[target].append(value)
            elif isinstance(value, list):
                for v in value:
                    if isinstance(v, dict) and 'v' in v: meta[target].append(v['v'])
    
    return {k: ", ".join(v) for k, v in meta.items()}


# --- 阶段一：快速获取列表 ---
def fetch_user_collection():
    """只获取基础列表 (API v0 /collections 不包含 infobox)"""
    if not ACCESS_TOKEN or not USERNAME: return None
    print(f"📡 [阶段一] 快速同步列表: {USERNAME} ...")
    
    all_items = []
    limit = 50
    offset = 0
    
    while True:
        url = f"https://api.bgm.tv/v0/users/{USERNAME}/collections"
        params = {"subject_type": 2, "limit": limit, "offset": offset}
        
        try:
            resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
            if resp.status_code != 200: break
            data = resp.json()
            items = data.get('data', [])
            if not items: break
            
            for item in items:
                subject = item.get('subject', {})
                if not subject: continue

                # 基础信息解析
                record = {
                    "id": subject.get('id'),
                    "title": subject.get('name_cn') or subject.get('name'),
                    "type": "anime",
                    "status": STATUS_MAP.get(item['type'], "watched"),
                    "score": item.get('rate', 0),
                    "tags": [t['name'] if isinstance(t, dict) else t for t in item.get('tags', []) if isinstance(t, (dict, str))],
                    "summary": subject.get('short_summary', '') or "暂无简介",
                    "updated_at": item.get('updated_at', ''),
                    # 初始化空字段，等待“阶段二”补全
                    "director": "", "script": "", "studio": "" 
                }
                
                # 尝试解析日期
                try:
                    parts = subject.get('date', '').split('-')
                    record['year'] = int(parts[0]) if len(parts) >= 1 and parts[0].isdigit() else 0
                    record['month'] = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 0
                except:
                    record['year'], record['month'] = 0, 0

                all_items.append(record)
            
            print(f"   ⬇️ 获取列表: {len(all_items)} 条...")
            offset += limit
            time.sleep(0.5)
            
        except Exception:
            traceback.print_exc()
            break
            
    return all_items

def fetch_subject_cast(subject_id):
    """
    🎤 专门获取声优信息
    API: GET /v0/subjects/{subject_id}/characters
    """
    url = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # data 是一个列表
            cv_list = []
            for char_item in data:
                # 只要主角和配角
                if char_item.get('relation') in ['主角', '配角']:
                    actors = char_item.get('actors', [])
                    if actors:
                        # 格式: 角色(声优) 或者 直接取声优
                        # 为了节省 Token，这里我们只取声优名字
                        cv_name = actors[0].get('name', '')
                        if cv_name:
                            cv_list.append(cv_name)
            
            # 取前 6 位主要声优，避免列表太长
            return ", ".join(list(set(cv_list))[:4])
    except Exception as e:
        print(f"   ⚠️ 获取CV失败: {e}")
    
    return ""

# --- 阶段二：补全缺失的详细信息 (Deep Sync) ---
def fill_missing_metadata(batch_limit=5):
    """
    深度补全：同时获取 制作信息(Infobox) 和 声优(Characters)
    """
    records = load_local_records()
    if not records: return "本地无数据"

    # 筛选条件：没有制作公司 OR 没有声优，且状态是想看/在看/搁置
    targets = [
        r for r in records 
        if (not r.get('studio') or not r.get('cv')) 
        # and r['status'] in ['wish', 'watching', 'on_hold']
    ]
    
    if not targets:
        return "✅ 所有待看番剧的元数据（含CV）已完整！"

    print(f"🛠️ [Deep Sync] 开始补全 (计划: {batch_limit} 条 / 剩余: {len(targets)} 条)...")
    
    updated_count = 0
    # 进度反馈用
    log_msgs = []

    for i, record in enumerate(targets[:batch_limit]):
        sid = record['id']
        title = record['title']
        logs = []
        
        try:
            # 1. 补全 Infobox (监督/公司)
            if not record.get('studio'):
                url_info = f"https://api.bgm.tv/v0/subjects/{sid}"
                resp = requests.get(url_info, headers=HEADERS, timeout=10)
                if resp.status_code == 200:
                    detail = resp.json()
                    meta = parse_infobox_info(detail.get('infobox', []))
                    record['director'] = meta.get('director', '')
                    record['script'] = meta.get('script', '')
                    record['studio'] = meta.get('studio', '')
                    # record['summary'] = detail.get('summary', record['summary'])
                    logs.append("制作信")
                time.sleep(1) # 间隔

            # 2. 补全 CV (声优)
            if not record.get('cv'):
                cv_str = fetch_subject_cast(sid)
                record['cv'] = cv_str
                logs.append("声优")
                time.sleep(1) # 间隔

            if logs:
                updated_count += 1
                log_msgs.append(f"✅ {title}: +{' & '.join(logs)}")
                print(f"   Updated {title}")

        except Exception as e:
            print(f"   ❌ {title} 失败: {e}")

    if updated_count > 0:
        save_records(records)
        return f"已补全 {updated_count} 部作品。\n" + "\n".join(log_msgs)
    else:
        return "⚠️ 本次尝试未产生有效更新（可能API超时）。"

# --- 主入口 ---
def sync_bangumi_to_local(deep_sync=False):
    # 1. 阶段一：列表同步
    cloud_data = fetch_user_collection()
    if not cloud_data: return "云端同步失败"
    
    local_data = load_local_records()
    local_map = {r['id']: r for r in local_data}
    
    new_cnt, upd_cnt = 0, 0
    for item in cloud_data:
        if item['id'] in local_map:
            # 保留本地已有的 deep info (如果有的话)
            old_record = local_map[item['id']]
            item['director'] = old_record.get('director', '')
            item['script'] = old_record.get('script', '')
            item['studio'] = old_record.get('studio', '')
            # 更新
            local_map[item['id']].update(item)
            upd_cnt += 1
        else:
            local_map[item['id']] = item
            new_cnt += 1
    
    save_records(list(local_map.values()))
    msg = f"✅ 列表同步完成 (新增{new_cnt}/更新{upd_cnt})。"
    
    # 2. 阶段二：如果是深度同步，或者有新想看的番，尝试补全一点点数据
    if deep_sync:
        msg += " " + fill_missing_metadata(batch_limit=10) # 每次补10个
    
    return msg

def get_missing_stats():
    """
    📊 获取当前数据的补全状态
    返回: (总数, 待补全数, 下一个待处理的ID)
    """
    records = load_local_records()
    if not records:
        return 0, 0, None
    
    # 筛选：想看/在看/搁置 且 (缺公司 或 缺声优)
    targets = [
        r for r in records 
        # if r['status'] in ['wish', 'watching', 'on_hold'] 
        # and (not r.get('studio') or not r.get('cv'))
        if (not r.get('studio') or not r.get('cv'))
    ]
    
    next_id = targets[0]['id'] if targets else None
    return len(records), len(targets), next_id

def patch_one_item(subject_id):
    """
    🐛 补全单条数据 (修复死循环版)
    """
    records = load_local_records()
    target = next((r for r in records if r['id'] == subject_id), None)
    
    if not target: 
        return False, "未找到记录"

    title = target['title']
    logs = []
    has_update = False

    try:
        # --- 1. 补全 Infobox (制作公司/监督) ---
        # 只要当前是空的，或者是"暂无"标记(防止有人手动改了想重试)，就尝试获取
        if not target.get('studio'):
            url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
            resp = requests.get(url, headers=HEADERS, timeout=10)
            
            if resp.status_code == 200:
                detail = resp.json()
                meta = parse_infobox_info(detail.get('infobox', []))
                
                # 🛠️ 关键修复：如果解析结果为空，填入 "暂无"，防止死循环
                new_director = meta.get('director', '') or "暂无监督"
                new_script = meta.get('script', '') or "暂无脚本"
                new_studio = meta.get('studio', '') or "暂无公司"
                
                target['director'] = new_director
                target['script'] = new_script
                target['studio'] = new_studio
                # target['summary'] = detail.get('summary', target['summary'])
                
                has_update = True
                logs.append("制作")
            
            time.sleep(1.0) # 礼貌间隔

        # --- 2. 补全 CV (声优) ---
        if not target.get('cv'):
            cv_str = fetch_subject_cast(subject_id)
            
            # 🛠️ 关键修复：如果没抓到CV，填入 "暂无CV"，防止下一轮重复抓取
            if cv_str:
                target['cv'] = cv_str
                logs.append("声优")
            else:
                target['cv'] = "暂无CV"
                logs.append("无声优记录")
                
            has_update = True # 即使是"暂无"，也算更新了状态，避免下次再查
            time.sleep(1.0)

        # --- 3. 保存 ---
        if has_update:
            save_records(records)
            return True, f"✅ {title}: +{'&'.join(logs)}"
        else:
            return True, f"⚠️ {title}: 无需更新"

    except Exception as e:
        return False, f"❌ {title} 失败: {e}"
    
def search_subject(keywords):
    """
    🔍 搜索番剧 (Tool)
    使用 Bangumi 搜索 API 找到最匹配的动画 ID
    """
    if not keywords: return None
    
    # URL 编码 (例如: "进击的巨人" -> "%E8%BF%9B...")
    safe_kw = urllib.parse.quote(keywords)
    
    # 使用经典的搜索接口，因为它对模糊匹配名字支持最好
    url = f"https://api.bgm.tv/search/subject/{safe_kw}?type=2&responseGroup=small&max_results=3"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            if 'list' in data and len(data['list']) > 0:
                return data['list'][0] # 返回匹配度最高的一个
    except Exception as e:
        print(f"❌ 搜索失败 [{keywords}]: {e}")
    return None

def get_subject_detail_v0(subject_id):
    """
    🧬 获取详情 (Tool)
    获取用于提取 'DNA' 的详细元数据 (Tags, Infobox)
    """
    url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=8)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None

if __name__ == "__main__":
    # 测试模式：开启深度同步
    print(sync_bangumi_to_local(deep_sync=True))