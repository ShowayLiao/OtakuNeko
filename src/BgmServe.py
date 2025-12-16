import os
import json
import time
import requests
import traceback
import urllib.parse
import io
from typing import Dict, List, Optional, Tuple, Any
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image

# 加载环境变量
load_dotenv()

class BangumiService:
    """
    Bangumi API 服务层
    负责：数据同步、元数据补全、搜索、图片下载
    """
    
    # --- 配置常量 ---
    DATA_DIR = "data"
    DATA_FILE = "bangumi_full_records.json"
    STATUS_MAP = {1: "wish", 2: "watched", 3: "watching", 4: "on_hold", 5: "dropped"}
    
    def __init__(self):
        # 初始化路径
        self.data_path = os.path.join(self.DATA_DIR, self.DATA_FILE)
        os.makedirs(self.DATA_DIR, exist_ok=True)

        # 加载凭证
        self.access_token = os.getenv("BGM_ACCESS_TOKEN")
        self.username = os.getenv("BGM_USERNAME")
        
        # 初始化网络会话 (带重试机制)
        self.session = self._init_session()
        self._local_db_cache: Optional[Dict[str, Dict]] = None  # 本地数据缓存，用于搜索加速

    def _init_session(self) -> requests.Session:
        """初始化带重试机制的 Session"""
        session = requests.Session()
        retry_strategy = Retry(
            total=3,  # 最大重试次数
            backoff_factor=1,  # 重试间隔 (1s, 2s, 4s)
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        session.headers.update({
            "User-Agent": "OtakuMate/2.0 (refactored_service)",
            "Authorization": f"Bearer {self.access_token}" if self.access_token else ""
        })
        return session

    # ==========================
    # 💾 本地数据管理 (CRUD)
    # ==========================

    def load_local_records(self) -> List[Dict]:
        """读取本地 JSON"""
        if not os.path.exists(self.data_path):
            return []
        try:
            with open(self.data_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"⚠️ 读取本地数据出错: {e}")
            return []

    def save_records(self, records: List[Dict]):
        """保存到本地 JSON"""
        try:
            with open(self.data_path, 'w', encoding='utf-8') as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 保存数据失败: {e}")

    # ==========================
    # 📡 核心同步逻辑 (Sync)
    # ==========================

    def fetch_user_collection(self) -> List[Dict]:
        """[阶段一] 快速获取用户收藏列表 (分页)"""
        if not self.username:
            print("❌ 未配置 BGM_USERNAME，无法同步。")
            return []

        print(f"📡 [Sync] 正在同步用户 {self.username} 的收藏...")
        all_items = []
        limit = 50
        offset = 0

        while True:
            url = f"https://api.bgm.tv/v0/users/{self.username}/collections"
            params = {"subject_type": 2, "limit": limit, "offset": offset}
            
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code != 200:
                    print(f"⚠️ API 错误 Code: {resp.status_code}")
                    break
                
                data = resp.json()
                items = data.get('data', [])
                if not items:
                    break

                for item in items:
                    subject = item.get('subject', {})
                    if not subject: continue
                    
                    # 基础字段解析
                    record = {
                        "id": subject.get('id'),
                        "title": subject.get('name_cn') or subject.get('name'),
                        "type": "anime",
                        "status": self.STATUS_MAP.get(item['type'], "watched"),
                        "score": item.get('rate', 0),
                        "tags": [t['name'] if isinstance(t, dict) else t for t in item.get('tags', []) if isinstance(t, (dict, str))],
                        "summary": subject.get('short_summary', '') or "暂无简介",
                        "image": subject.get('images', {}).get('large', ''), # 顺便存个图
                        "updated_at": item.get('updated_at', ''),
                        # 占位符，等待 Deep Sync
                        "director": "", "script": "", "studio": "", "cv": ""
                    }
                    all_items.append(record)
                
                print(f"   ⬇️ 已获取 {len(all_items)} 条...")
                offset += limit
                time.sleep(0.5)

            except Exception as e:
                traceback.print_exc()
                break
        
        return all_items

    def _fetch_extra_metadata(self, subject_id: int) -> Dict[str, str]:
        """
        [内部工具] 获取单个条目的深度信息 (制作人员 + 声优)
        返回: {"director":..., "cv":...}
        """
        result = {"director": "", "script": "", "studio": "", "cv": ""}
        
        # 1. 获取 Infobox (制作信息)
        try:
            url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                meta = self._parse_infobox(data.get('infobox', []))
                result.update(meta)
        except Exception:
            pass
            
        time.sleep(0.5) # 稍微歇一下

        # 2. 获取 Character (声优)
        try:
            url_cv = f"https://api.bgm.tv/v0/subjects/{subject_id}/characters"
            resp = self.session.get(url_cv, timeout=10)
            if resp.status_code == 200:
                cv_data = resp.json()
                cv_list = []
                for char in cv_data:
                    if char.get('relation') in ['主角', '配角']:
                        actors = char.get('actors', [])
                        if actors:
                            cv_list.append(actors[0].get('name', ''))
                result['cv'] = ", ".join(list(set(cv_list))[:5])
        except Exception:
            pass

        return result

    def _parse_infobox(self, infobox: List) -> Dict[str, str]:
        """解析 API 返回的 infobox 列表"""
        if not infobox: return {}
        meta = {"director": [], "script": [], "studio": []}
        key_map = {
            "导演": "director", "监督": "director", 
            "脚本": "script", "系列构成": "script",
            "动画制作": "studio", "制作公司": "studio"
        }
        for item in infobox:
            key = item.get('key')
            if key in key_map:
                val = item.get('value')
                target = key_map[key]
                if isinstance(val, str): meta[target].append(val)
                elif isinstance(val, list):
                    for v in val:
                        if isinstance(v, dict) and 'v' in v: meta[target].append(v['v'])
        
        return {k: ", ".join(v) for k, v in meta.items()}

    def run_sync(self, deep_sync=False) -> str:
        """
        🚀 执行完整同步流程
        1. 快速拉取列表
        2. 合并本地数据
        3. (可选) 深度补全元数据
        """
        cloud_data = self.fetch_user_collection()
        if not cloud_data: return "❌ 云端同步失败"

        local_data = self.load_local_records()
        local_map = {r['id']: r for r in local_data}
        
        new_cnt, upd_cnt = 0, 0
        
        # --- 合并逻辑 ---
        for item in cloud_data:
            sid = item['id']
            if sid in local_map:
                # 保留本地已经辛苦抓取的 deep info
                old = local_map[sid]
                item['director'] = old.get('director', '')
                item['script'] = old.get('script', '')
                item['studio'] = old.get('studio', '')
                item['cv'] = old.get('cv', '')
                
                local_map[sid].update(item)
                upd_cnt += 1
            else:
                local_map[sid] = item
                new_cnt += 1
        
        merged_list = list(local_map.values())
        self.save_records(merged_list)
        msg = f"✅ 基础同步完成 (新增 {new_cnt} / 更新 {upd_cnt})。"

        # --- Deep Sync (补全缺失) ---
        if deep_sync:
            msg += "\n" + self._fill_missing_metadata(merged_list)
        
        return msg

    def _fill_missing_metadata(self, records: List[Dict], batch_limit=10) -> str:
        """[阶段二] 补全缺失的元数据"""
        # 筛选：缺数据 且 (在看/想看/搁置/已看)
        targets = [
            r for r in records 
            if (not r.get('studio') or not r.get('cv')) 
            # 这里的筛选策略可以根据需要调整，目前是对所有缺失的都尝试补全
        ]
        
        if not targets: return "✅ 元数据已完整。"
        
        print(f"🛠️ [Deep Sync] 发现 {len(targets)} 条缺失，正在补全前 {batch_limit} 条...")
        
        logs = []
        count = 0
        
        for record in targets[:batch_limit]:
            sid = record['id']
            title = record['title']
            
            # 获取数据
            meta = self._fetch_extra_metadata(sid)
            
            # 填入数据 (如果没有抓到，填入'暂无'防止死循环)
            record['director'] = meta['director'] or record.get('director') or "暂无"
            record['script'] = meta['script'] or record.get('script') or "暂无"
            record['studio'] = meta['studio'] or record.get('studio') or "暂无"
            record['cv'] = meta['cv'] or record.get('cv') or "暂无"
            
            logs.append(f"📦 补全: {title}")
            count += 1
            print(f"   updated: {title}")
        
        if count > 0:
            self.save_records(records)
            
        return f"已补全 {count} 条元数据。"

    # ==========================
    # 🛠️ Agent 工具函数 (Tools)
    # ==========================

    # ==========================
    # 🔍 智能搜索模块 
    # ==========================

    def _ensure_local_db(self):
        """确保本地查找表已建立 (Lazy Loading)"""
        if self._local_db_cache is None:
            records = self.load_local_records()
            # 建立 title -> record 的映射
            # 如果有重名，后面的会覆盖前面的，问题不大
            self._local_db_cache = {r['title']: r for r in records if r.get('title')}

    def _find_best_local_match(self, query_title: str) -> Optional[Dict]:
        """
        在本地库中寻找最佳匹配项 (移植自 ProfileAgent)
        策略：
        1. 精确匹配
        2. 忽略大小写匹配
        3. 子串匹配 (AI 标题是 DB 标题的一部分，或者反过来)
        """
        if not query_title or query_title == "N/A": return None
        
        self._ensure_local_db()
        local_db = self._local_db_cache
        
        # 1. 精确匹配 (Hash Map O(1))
        if query_title in local_db:
            return local_db[query_title]

        # 准备数据进行遍历匹配
        query_norm = query_title.lower().strip()
        
        # 2. 遍历查找 (O(N)) - 本地数据通常 < 5000，速度很快
        candidates = []
        for db_title, item in local_db.items():
            db_norm = db_title.lower().strip()
            
            # Case A: AI 标题是 DB 标题的子串 (例如 AI: "Fate HF", DB: "剧场版 Fate HF")
            if query_norm in db_norm:
                diff = len(db_norm) - len(query_norm)
                candidates.append((diff, item))
                continue
                
            # Case B: DB 标题是 AI 标题的子串 (罕见，但防止 AI 加了奇怪后缀)
            if db_norm in query_norm:
                diff = len(query_norm) - len(db_norm)
                candidates.append((diff, item))
                continue

        # 如果有候选，返回长度差最小的那个 (匹配度最高)
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        return None
    
    def _fetch_image_by_id(self, subject_id: int) -> str:
        """
        [内部助手] 已知 ID，通过 API 获取图片 URL
        因为 Bangumi 图片 URL 包含随机哈希，无法直接合成，必须查。
        """
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        try:
            resp = self.session.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                images = data.get('images') or {}
                # 优先取 large，没有取 common
                return images.get('large') or images.get('common') or ""
        except Exception:
            pass
        return ""

    def search_subject(self, keywords: str) -> Optional[Dict]:
        """
        🔍 智能搜索条目 (标准流程版)
        流程: 关键词 -> [本地查ID / 联网搜ID] -> 拿到ID -> v0接口查详情 -> 清洗数据
        """
        import urllib.parse
        
        if not keywords: return None
        
        subject_id = None
        
        # --- Step 1: 获取 Subject ID (本地优先 -> 网络兜底) ---
        
        # 1.1 尝试本地匹配
        local_match = self._find_best_local_match(keywords)
        if local_match:
            subject_id = local_match['id']
            print(f" ⚡ 本地命中关键词: '{keywords}' -> ID: {subject_id}")
        else:
            # 1.2 本地未找到，启动网络关键词搜索获取 ID
            print(f" 🔍 本地未找到，启动网络搜索 ID: {keywords} ...")
            safe_kw = urllib.parse.quote(keywords)
            # 仅搜索 ID，不需要太详细，所以 responseGroup=small 够了
            search_url = f"https://api.bgm.tv/search/subject/{safe_kw}?type=2&responseGroup=small&max_results=1"
            
            try:
                resp = self.session.get(search_url, timeout=8)
                if resp.status_code == 200:
                    data = resp.json()
                    if 'list' in data and data['list']:
                        first_result = data['list'][0]
                        subject_id = first_result['id']
                        print(f" 🌐 网络搜索命中: {first_result.get('name_cn') or first_result.get('name')} -> ID: {subject_id}")
                    else:
                        print(" ⚠️ 网络搜索未找到相关条目")
            except Exception as e:
                print(f" ❌ 网络搜索 ID 失败: {e}")

        # --- Step 2 & 3: 拿到 ID 后，统一获取详情并清洗 ---
        
        if subject_id:
            print(f" 🚀 正在通过 v0 接口拉取详情 (ID:{subject_id})...")
            detail_url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
            
            try:
                # v0 接口建议带上 Accept header
                headers = {"User-Agent": "OtakuMate/1.0", "Accept": "application/json"}
                resp = self.session.get(detail_url, headers=headers, timeout=10)
                
                if resp.status_code == 200:
                    raw_data = resp.json()
                    
                    # --- Step 3: 数据清洗 (Data Cleaning) ---
                    # 将 v0 的复杂结构转化为 UI 需要的扁平结构
                    
                    # 3.1 提取评分 (处理嵌套和缺失情况)
                    score = 0
                    if 'rating' in raw_data and isinstance(raw_data['rating'], dict):
                        score = raw_data['rating'].get('score', 0)
                        
                    # 3.2 提取图片 (v0 返回的就是标准字典，直接用)
                    images = raw_data.get('images', {})
                    
                    # 3.3 提取标题 (优先中文)
                    title = raw_data.get('name_cn') or raw_data.get('name')
                    
                    # 3.4 提取简介并生成短评
                    # summary = raw_data.get('summary', '')
                    # 简单的短评逻辑：取简介前60字
                    # short_comment = summary[:60] + "..." if summary else "暂无简介"

                    # 3.5 构造最终清洗后的字典
                    clean_data = {
                        'id': raw_data.get('id'),
                        'name_cn': title,
                        'images': images,       # 格式: {'large': '...', 'common': '...'}
                        'score': score,        # 格式: 7.5 (float) 或 0
                        # 'summary': summary,    # 完整简介
                        # 'comment': short_comment, # 用于卡片显示的短文本
                        # 'type': raw_data.get('type'),
                        # 保留 info_box 等其他可能需要的数据，也可以在这里加
                    }
                    
                    return clean_data
                else:
                    print(f" ⚠️ 获取详情失败 Code: {resp.status_code}")
                    
            except Exception as e:
                print(f" ❌ 详情数据拉取异常: {e}")

        return None

    def get_subject_detail(self, subject_id: int) -> Optional[Dict]:
        """获取详情 (供 Agent 使用)"""
        try:
            url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
            resp = self.session.get(url, timeout=8)
            if resp.status_code == 200:
                return resp.json()
        except: pass
        return None

    def download_image(self, url: str) -> Optional[Image.Image]:
        """
        🖼️ 下载图片并转为 PIL 对象 (供 ProfileAgent 绘图使用)
        """
        if not url: return None
        try:
            resp = self.session.get(url, timeout=15)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content))
        except Exception:
            pass
        return None

    def get_missing_stats(self) -> Tuple[int, int, Optional[int]]:
        """
        📊 获取补全进度
        Returns: (总记录数, 待补全数, 下一个待处理ID)
        """
        records = self.load_local_records()
        if not records:
            return 0, 0, None
        
        # 筛选条件：缺制作公司 OR 缺声优
        targets = [
            r for r in records 
            if (not r.get('studio') or not r.get('cv'))
        ]
        
        next_id = targets[0]['id'] if targets else None
        return len(records), len(targets), next_id

    def patch_one_item(self, subject_id: int) -> Tuple[bool, str]:
        """
        🐛 修复单条数据的元数据
        Returns: (是否成功, 日志消息)
        """
        records = self.load_local_records()
        # 找到对应的记录引用
        target = next((r for r in records if r['id'] == subject_id), None)
        
        if not target: 
            return False, f"ID {subject_id} 本地未找到"

        title = target['title']
        
        try:
            # 复用类内部的抓取逻辑
            meta = self._fetch_extra_metadata(subject_id)
            
            # 更新数据 (如果没抓到，填入暂无，防止死循环)
            target['director'] = meta['director'] or target.get('director') or "暂无"
            target['script'] = meta['script'] or target.get('script') or "暂无"
            target['studio'] = meta['studio'] or target.get('studio') or "暂无"
            target['cv'] = meta['cv'] or target.get('cv') or "暂无"
            
            # 保存
            self.save_records(records)
            return True, f"✅ 已补全: {title}"
            
        except Exception as e:
            return False, f"❌ {title} 失败: {e}"
        
    def extract_score(self, subject_data):
        if not subject_data: return 'N/A'
        rating = subject_data.get('rating')
        if rating and isinstance(rating, dict):
            score = rating.get('score')
            if score and score > 0: return score
        score = subject_data.get('score')
        if score and score > 0: return score
        return 'N/A'

# --- 单例模式 (可选) ---
# 这样其他文件 import bgm_service 就能直接用
bgm_service = BangumiService()

if __name__ == "__main__":
    # 测试入口
    print("🚀 开始同步...")
    print(bgm_service.run_sync(deep_sync=True))