import sys
import os
from datetime import datetime, timezone

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from app.schemas.adaptersV2 import bangumi_collection_to_collectionlist

# 测试数据：使用bangumi_collection.json中的实际格式
test_data = {
    "data": [{
        "updated_at": "2025-12-27T02:01:26+08:00",  # 实际Bangumi API返回的格式
        "comment": None,
        "tags": [],
        "subject": {
            "date": "2025-10-04",
            "images": {
                "small": "https://lain.bgm.tv/r/200/pic/cover/l/3d/79/498378_3ycrL.jpg",
                "grid": "https://lain.bgm.tv/r/100/pic/cover/l/3d/79/498378_3ycrL.jpg",
                "large": "https://lain.bgm.tv/pic/cover/l/3d/79/498378_3ycrL.jpg",
                "medium": "https://lain.bgm.tv/r/800/pic/cover/l/3d/79/498378_3ycrL.jpg",
                "common": "https://lain.bgm.tv/r/400/pic/cover/l/3d/79/498378_3ycrL.jpg"
            },
            "name": "SPY×FAMILY Season 3",
            "name_cn": "间谍过家家 第三季",
            "short_summary": "测试简介",
            "tags": [],
            "score": 7.4,
            "type": 2,
            "id": 498378,
            "eps": 13,
            "volumes": 0,
            "collection_total": 12828,
            "rank": 1242
        },
        "subject_id": 498378,
        "vol_status": 0,
        "ep_status": 12,
        "subject_type": 2,
        "type": 3,
        "rate": 0,
        "private": False
    }]
}

# 运行测试
print("测试Bangumi API格式的updated_at处理")
try:
    result = bangumi_collection_to_collectionlist(test_data, 1)
    if result.collections:
        collection = result.collections[0]
        print(f"  成功转换，updated_at类型: {type(collection.updated_at)}")
        print(f"  updated_at值: {collection.updated_at}")
        print(f"  转换后的时区: {collection.updated_at.tzinfo}")
    else:
        print(f"  转换失败，没有生成collection")
except Exception as e:
    print(f"  错误: {e}")

print("\n测试完成！")
