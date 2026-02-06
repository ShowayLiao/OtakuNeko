import sys
import os
from datetime import datetime, timezone

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from app.schemas.adaptersV2 import bangumi_collection_to_collectionlist
from app.schemas.collection import CollectionUpsertList

# 测试数据：使用bangumi_collection.json中的实际格式
test_data = {
    "data": [{
        "updated_at": "2025-12-27T02:01:26+08:00",
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
print("测试batch_upsert操作")
try:
    # 转换数据
    result = bangumi_collection_to_collectionlist(test_data, 1)
    print(f"  转换成功，生成了 {result.total} 条记录")
    
    # 检查生成的CollectionUpsert对象
    if result.collections:
        collection = result.collections[0]
        print(f"  生成的CollectionUpsert对象:")
        print(f"    user_id: {collection.user_id}")
        print(f"    source: {collection.source}")
        print(f"    source_id: {collection.source_id}")
        print(f"    updated_at: {collection.updated_at}")
        print(f"    type: {collection.type}")
        print(f"    rate: {collection.rate}")
        print(f"    subject_type: {collection.subject_type}")
        print(f"    private: {collection.private}")
        print(f"    tags: {collection.tags}")
        print(f"    vol_status: {collection.vol_status}")
        print(f"    ep_status: {collection.ep_status}")
        
        # 检查id字段是否存在（应该不存在，因为CollectionUpsert不包含id字段）
        if hasattr(collection, 'id'):
            print(f"    id: {collection.id}")
        else:
            print(f"    id: 不存在（正常，CollectionUpsert不包含id字段）")
            
    print("\n测试完成！")
except Exception as e:
    print(f"  错误: {e}")
    import traceback
    traceback.print_exc()

print("\n测试完成！")
