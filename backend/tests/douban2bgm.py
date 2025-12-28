import json

def convert_douban_to_bangumi(json_data, index):
    """
    输入豆瓣数据对象和序号，输出 Bangumi 格式的 JSON
    """
    
    # 1. 获取指定序号的条目
    # 这里的逻辑兼容了两种常见的豆瓣数据结构（根节点是列表，或根节点是字典包含 "interest"）
    try:
        if isinstance(json_data, dict) and "interest" in json_data:
            douban_item = json_data["interest"][index]
        elif isinstance(json_data, list):
            douban_item = json_data[index]
        else:
            return {"error": "无法识别的 JSON 结构"}
    except IndexError:
        return {"error": f"找不到序号为 {index} 的条目 (总数: {len(json_data.get('interest', []))})"}

    # 2. 定义状态映射表 (Status Mapping)
    # 根据你的需求，这里将豆瓣的状态字符串映射为 Bangumi 的 type 数字
    status_map = {
        "wish": 1,        # 想看/想读
        "collect": 2,     # 看过/读过
        "mark": 2,        # 豆瓣"标记"通常指看过，但如果你想对应"在看"，可改为 3
        "do": 3,          # 在看/在读
        "reading": 3,     # 在读
        "on_hold": 4,     # 搁置
        "dropped": 5      # 抛弃
    }

    # 定义条目类型映射表 (Subject Type Mapping)
    # 豆瓣的 type 映射到 Bangumi 的 subject_type 数字
    # Bangumi: 1-书籍, 2-动画, 3-音乐, 4-游戏, 6-三次元
    subject_type_map = {
        "book": 1,        # 书籍
        "movie": 6,       # 三次元（电影）
        "tv": 6,          # 三次元（电视剧）
        "music": 3,       # 音乐
        "game": 4         # 游戏
    }

    # 获取当前条目的状态
    db_status = douban_item.get("status", "")
    # 默认映射为 2 (看过)，如果在表中找不到对应的 key
    bgm_type = status_map.get(db_status, 2)

    # 获取条目类型
    db_subject_type = douban_item.get("type", "")
    # 默认映射为 1 (书籍)，如果在表中找不到对应的 key
    bgm_subject_type = subject_type_map.get(db_subject_type, 1)

    # 3. 提取主体信息 (Subject Info)
    # 豆瓣的数据嵌套在 'interest' 字段中 [cite: 4]
    db_interest = douban_item.get("interest", {})
    db_subject = douban_item.get("interest", {}).get("subject", {})
    
    # 提取封面图 (优先取 large，没有则取 normal) 
    cover_url = db_subject.get("pic", {}).get("large", "") or db_subject.get("pic", {}).get("normal", "")
    if db_interest.get("rating", {}):
        rate = db_interest.get("rating", {}).get("value", 0)
    else:
        rate = 0

    # 转换 tags 格式为 Bangumi 格式
    db_tags = db_subject.get("genres", [])
    bangumi_tags = []
    for tag in db_tags:
        if isinstance(tag, str):
            bangumi_tags.append({
                "name": tag,
                "count": 0,
                "total_cont": 0
            })
        elif isinstance(tag, dict):
            bangumi_tags.append({
                "name": tag.get("name", ""),
                "count": tag.get("count", 0),
                "total_cont": tag.get("total_cont", 0)
            })

    # 4. 构建 Bangumi 数据结构
    # 参照你提供的 Bangumi 数据样例 
    bangumi_data = {
        "updated_at": db_interest.get("create_time", ""), # 更新时间 [cite: 3]
        "comment": db_interest.get("comment", "") if db_interest.get("comment", "") else None,        # 短评 [cite: 2]
        "tags": db_interest.get("tags", []),              # 标签
        "subject": {
            "date": db_subject.get("pubdate", [""])[0],            # 发行日期 [cite: 6]
            "images": {
                "large": cover_url,
                "common": cover_url,
                "medium": cover_url,
                "small": cover_url,
                "grid": cover_url
            },
            "name": db_subject.get("title", ""),    # 标题 [cite: 19]
            # 豆瓣通常只给一个 title，这里同时填入中文名字段作为兜底
            "name_cn": db_subject.get("title", ""), 
            "short_summary": db_subject.get("intro", ""),  # 简介 [cite: 19]
            "tags": bangumi_tags,              # 标签
            "score": db_subject.get("rating", {}).get("value", 0), # 大众评分 [cite: 5]
            "id": int(db_subject.get("id", 0)),  # 条目 ID [cite: 19]
            "type": bgm_type,  # 这个是看过/读过/在看/在读/搁置/抛弃
            "eps": 0,          # 总集数（豆瓣没有此字段，默认为0）
            "volumes": 0,      # 总卷数（豆瓣没有此字段，默认为0）
            "collection_total": 0,  # 收藏状态（豆瓣没有此字段，默认为0）
            "rank": 0,  # 排名 [cite: 5]
            # 尝试获取作者信息，如果是数组则转为字符串

            
        },
        "subject_id": int(db_subject.get("id", 0)), # 条目 ID
        "vol_status": 0,    # 卷数状态（豆瓣没有此字段，默认为0）
        "ep_status": 0,     # 集数状态（豆瓣没有此字段，默认为0）
        "subject_type": bgm_subject_type,  # 条目类型，这个是动画/漫画/游戏/书籍/三次元
        "type": bgm_type,   # 对应 Bangumi 的收藏状态 (1-5)
        "rate": rate, # 用户评分
        "private": db_interest.get("is_private", False),  # 私密状态 [cite: 4]
        
    }

    return bangumi_data

# ==========================================
# 示例运行
# ==========================================

import sys


json_file_path = "tofu[208745052].json"
target_index = 150

try:
    with open(json_file_path, 'r', encoding='utf-8') as f:
        input_json = json.load(f)
except FileNotFoundError:
    print(f"错误: 找不到文件 {json_file_path}")
    sys.exit(1)
except json.JSONDecodeError as e:
    print(f"错误: JSON 格式不正确 - {e}")
    sys.exit(1)

# 执行转换
result = convert_douban_to_bangumi(input_json, target_index)

# Print 结果 (ensure_ascii=False 用于正确显示中文)
print(json.dumps(result, indent=4, ensure_ascii=False))