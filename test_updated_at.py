import sys
import os
from datetime import datetime, timezone

# 添加backend目录到Python路径
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

from app.schemas.adaptersV2 import bangumi_collection_to_collectionlist

# 测试数据
test_cases = [
    # 测试1: ISO格式的字符串
    {
        "name": "ISO格式字符串",
        "data": {
            "data": [{
                "subject_id": 1,
                "type": 2,
                "rate": 8,
                "updated_at": "2023-12-01T12:00:00",
                "subject": {
                    "id": 1,
                    "type": 2,
                    "name": "测试动画"
                }
            }]
        }
    },
    # 测试2: 普通格式的字符串
    {
        "name": "普通格式字符串",
        "data": {
            "data": [{
                "subject_id": 2,
                "type": 3,
                "rate": 9,
                "updated_at": "2023-12-01 12:00:00",
                "subject": {
                    "id": 2,
                    "type": 2,
                    "name": "测试动画2"
                }
            }]
        }
    },
    # 测试3: 格式不正确的字符串
    {
        "name": "格式不正确的字符串",
        "data": {
            "data": [{
                "subject_id": 3,
                "type": 1,
                "rate": 7,
                "updated_at": "2023/12/01",
                "subject": {
                    "id": 3,
                    "type": 2,
                    "name": "测试动画3"
                }
            }]
        }
    },
    # 测试4: 数字类型
    {
        "name": "数字类型",
        "data": {
            "data": [{
                "subject_id": 4,
                "type": 4,
                "rate": 6,
                "updated_at": 1670000000,
                "subject": {
                    "id": 4,
                    "type": 2,
                    "name": "测试动画4"
                }
            }]
        }
    },
    # 测试5: 空值
    {
        "name": "空值",
        "data": {
            "data": [{
                "subject_id": 5,
                "type": 5,
                "rate": 5,
                "updated_at": None,
                "subject": {
                    "id": 5,
                    "type": 2,
                    "name": "测试动画5"
                }
            }]
        }
    }
]

# 运行测试
for test_case in test_cases:
    print(f"\n测试: {test_case['name']}")
    try:
        result = bangumi_collection_to_collectionlist(test_case['data'], 1)
        if result.collections:
            collection = result.collections[0]
            print(f"  成功转换，updated_at类型: {type(collection.updated_at)}")
            print(f"  updated_at值: {collection.updated_at}")
        else:
            print(f"  转换失败，没有生成collection")
    except Exception as e:
        print(f"  错误: {e}")

print("\n测试完成！")
