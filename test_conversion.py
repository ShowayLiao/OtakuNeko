from backend.app.schemas.collection import CollectionRead, CollectionReadList
from backend.app.schemas.subject import SubjectRead, SubjectReadList
from backend.app.schemas.adaptersV2 import convert_to_collection_subject_list
from app.models.enums import SubjectType, CollectionStatus

# 创建测试数据
test_subjects = SubjectReadList(
    total=2,
    items=[
        SubjectRead(
            id=1,
            name="测试动画1",
            name_cn="测试动画1",
            type=SubjectType.ANIME,
            source="bangumi",
            source_id="123",
            summary="测试动画1简介",
            date="2023-01-01",
            platform="TV",
            eps=12,
            volumes=0,
            images={"common": "test1.jpg"},
            image="test1.jpg",
            tags=[{"name": "测试", "count": 10}],
            meta_tags=["测试", "动画"],
            infobox=[{"key": "作者", "value": "测试作者"}],
            rating={"score": 8.5},
            collection={"wish": 100, "collect": 200},
            series=False,
            locked=False,
            nsfw=False
        ),
        SubjectRead(
            id=2,
            name="测试游戏1",
            name_cn="测试游戏1",
            type=SubjectType.GAME,
            source="bangumi",
            source_id="456",
            summary="测试游戏1简介",
            date="2023-02-01",
            platform="PC",
            eps=0,
            volumes=0,
            images={"common": "test2.jpg"},
            image="test2.jpg",
            tags=[{"name": "测试", "count": 5}],
            meta_tags=["测试", "游戏"],
            infobox=[{"key": "开发商", "value": "测试开发商"}],
            rating={"score": 9.0},
            collection={"wish": 50, "collect": 100},
            series=False,
            locked=False,
            nsfw=False
        )
    ]
)

test_collections = CollectionReadList(
    total=2,
    items=[
        CollectionRead(
            user_id=1,
            source="bangumi",
            source_id="123",
            type=CollectionStatus.COMPLETED,
            rate=9,
            comment="非常好看",
            private=False,
            tags=["好看", "推荐"],
            vol_status=0,
            ep_status=12,
            subject_type=SubjectType.ANIME,
            updated_at="2023-03-01T00:00:00"
        ),
        CollectionRead(
            user_id=1,
            source="bangumi",
            source_id="456",
            type=CollectionStatus.PLANNED,
            rate=0,
            comment="",
            private=False,
            tags=[],
            vol_status=0,
            ep_status=0,
            subject_type=SubjectType.GAME,
            updated_at="2023-03-02T00:00:00"
        )
    ]
)

# 测试转换函数
result = convert_to_collection_subject_list(test_collections, test_subjects)

# 打印结果
print(f"转换成功！")
print(f"总记录数: {result.total}")
print(f"转换后的条目数: {len(result.items)}")

for i, item in enumerate(result.items):
    print(f"\n条目 {i+1}:")
    print(f"  用户ID: {item.user_id}")
    print(f"  来源: {item.source}")
    print(f"  来源ID: {item.source_id}")
    print(f"  类型: {item.type}")
    print(f"  评分: {item.rate}")
    print(f"  评论: {item.comment}")
    print(f"  私有: {item.private}")
    print(f"  标签: {item.tags}")
    print(f"  卷状态: {item.vol_status}")
    print(f"  集状态: {item.ep_status}")
    print(f"  条目类型: {item.subject_type}")
    print(f"  更新时间: {item.updated_at}")
    print(f"  关联条目: {item.subject.name if item.subject else '无'}")
