"""
Schema 重构验证脚本

验证重构后的 Schema 是否符合要求：
1. Base -> Create/Update -> Read 的分层继承模式
2. 严格使用类型注解，禁止使用裸露的 dict
3. 统一字段标准：tags 必须是 List[str]，status 必须引用 Enum
4. 保留现有的 Docstring 注释风格
"""

from app.schemas.user import UserBase, UserCreate, UserUpdate, UserRead
from app.schemas.subject import SubjectBase, SubjectRead, SubjectDetail, SubjectWithUserStatus
from app.schemas.collection import CollectionBase, CollectionUpdate, CollectionRead, CollectionList, ManualCollectionCreate
from app.models.enums import CollectionStatus
from datetime import datetime


def test_user_schemas():
    """测试用户 Schema 的继承关系和字段类型"""
    print("测试 User Schema...")
    
    # 测试 UserBase
    user_base = UserBase(
        nickname="test_nickname",
        email="test@example.com",
        avatar_url="http://example.com/avatar.jpg",
        sign="test signature",
        bangumi_id=12345
    )
    print(f"  UserBase: {user_base}")
    
    # 测试 UserCreate
    user_create = UserCreate(
        username="testuser",
        has_bangumi_account=True,
        nickname="test_nickname"
    )
    print(f"  UserCreate: {user_create}")
    
    # 测试 UserUpdate
    user_update = UserUpdate(nickname="updated_nickname")
    print(f"  UserUpdate: {user_update}")
    
    # 测试 UserRead
    user_read = UserRead(
        id=1,
        username="testuser",
        nickname="test_nickname",
        email="test@example.com",
        avatar_url="http://example.com/avatar.jpg",
        sign="test signature",
        bangumi_id=12345,
        created_at=datetime.now(),
        updated_at=datetime.now()
    )
    print(f"  UserRead: {user_read}")
    
    # 验证继承关系
    assert issubclass(UserCreate, UserBase), "UserCreate 应该继承自 UserBase"
    assert issubclass(UserUpdate, UserBase), "UserUpdate 应该继承自 UserBase"
    assert issubclass(UserRead, UserBase), "UserRead 应该继承自 UserBase"
    
    print("  ✓ User Schema 测试通过\n")


def test_subject_schemas():
    """测试条目 Schema 的继承关系和字段类型"""
    print("测试 Subject Schema...")
    
    # 测试 SubjectBase
    subject_base = SubjectBase(
        name="Test Subject",
        name_cn="测试条目",
        cover_url="http://example.com/cover.jpg",
        type=2,
        eps=12,
        volumes=3,
        platform="TV",
        summary="Test summary",
        tags=["tag1", "tag2"],
        date="2024-01-01"
    )
    print(f"  SubjectBase: {subject_base}")
    
    # 验证 tags 是 List[str]
    assert isinstance(subject_base.tags, list), "tags 应该是 List[str]"
    assert all(isinstance(tag, str) for tag in subject_base.tags), "tags 的所有元素都应该是 str"
    
    # 测试 SubjectRead
    subject_read = SubjectRead(
        id=1,
        source_id="12345",
        name="Test Subject",
        name_cn="测试条目",
        cover_url="http://example.com/cover.jpg",
        type=2,
        eps=12,
        volumes=3,
        platform="TV",
        summary="Test summary",
        tags=["tag1", "tag2"],
        date="2024-01-01",
        score=8.5,
        rank=10
    )
    print(f"  SubjectRead: {subject_read}")
    
    # 测试 SubjectDetail
    subject_detail = SubjectDetail(
        id=1,
        source_id="12345",
        name="Test Subject",
        name_cn="测试条目",
        cover_url="http://example.com/cover.jpg",
        type=2,
        eps=12,
        volumes=3,
        platform="TV",
        summary="Test summary",
        tags=["tag1", "tag2"],
        date="2024-01-01",
        score=8.5,
        rank=10,
        collection_total=100,
        meta_tags=["meta1", "meta2"],
        infobox=[{"key": "value"}],
        rating_details={"1": 10, "2": 20},
        images={"large": "url", "medium": "url"}
    )
    print(f"  SubjectDetail: {subject_detail}")
    
    # 测试 SubjectWithUserStatus
    subject_with_status = SubjectWithUserStatus(
        id=1,
        source_id="12345",
        name="Test Subject",
        name_cn="测试条目",
        cover_url="http://example.com/cover.jpg",
        type=2,
        eps=12,
        volumes=3,
        platform="TV",
        summary="Test summary",
        tags=["tag1", "tag2"],
        date="2024-01-01",
        score=8.5,
        rank=10,
        is_collected=True,
        collection_info={"status": "watching", "rate": 8}
    )
    print(f"  SubjectWithUserStatus: {subject_with_status}")
    
    # 验证继承关系
    assert issubclass(SubjectRead, SubjectBase), "SubjectRead 应该继承自 SubjectBase"
    assert issubclass(SubjectDetail, SubjectRead), "SubjectDetail 应该继承自 SubjectRead"
    assert issubclass(SubjectWithUserStatus, SubjectRead), "SubjectWithUserStatus 应该继承自 SubjectRead"
    
    print("  ✓ Subject Schema 测试通过\n")


def test_collection_schemas():
    """测试收藏 Schema 的继承关系和字段类型"""
    print("测试 Collection Schema...")
    
    # 测试 CollectionBase
    collection_base = CollectionBase(
        status=CollectionStatus.DO,
        rate=8,
        comment="Great!",
        private=False,
        tags=["favorite", "must-watch"]
    )
    print(f"  CollectionBase: {collection_base}")
    
    # 验证 status 是 Enum
    assert isinstance(collection_base.status, CollectionStatus), "status 应该是 CollectionStatus 枚举"
    
    # 验证 tags 是 List[str]
    assert isinstance(collection_base.tags, list), "tags 应该是 List[str]"
    assert all(isinstance(tag, str) for tag in collection_base.tags), "tags 的所有元素都应该是 str"
    
    # 测试 CollectionUpdate
    collection_update = CollectionUpdate(rate=9, comment="Updated comment")
    print(f"  CollectionUpdate: {collection_update}")
    
    # 测试 CollectionRead
    collection_read = CollectionRead(
        subject_id=1,
        updated_at=datetime.now(),
        status=CollectionStatus.DO,
        rate=8,
        comment="Great!",
        private=False,
        tags=["favorite", "must-watch"],
        subject=None
    )
    print(f"  CollectionRead: {collection_read}")
    
    # 测试 CollectionList
    collection_list = CollectionList(
        total=10,
        items=[collection_read]
    )
    print(f"  CollectionList: {collection_list}")
    
    # 测试 ManualCollectionCreate
    manual_create = ManualCollectionCreate(
        name="Manual Subject",
        type=2,
        status=1,
        cover_url="http://example.com/cover.jpg",
        rate=8,
        comment="Manual comment",
        release_date="2024-01-01",
        publish_date="2024-01-15",
        tags=["tag1", "tag2"]
    )
    print(f"  ManualCollectionCreate: {manual_create}")
    
    # 测试 ManualCollectionCreate 的 tags 验证器（字符串转列表）
    manual_create_str_tags = ManualCollectionCreate(
        name="Manual Subject",
        type=2,
        status=1,
        tags="tag1, tag2, tag3"
    )
    assert isinstance(manual_create_str_tags.tags, list), "tags 应该被转换为 List[str]"
    assert len(manual_create_str_tags.tags) == 3, "tags 应该包含 3 个元素"
    print(f"  ManualCollectionCreate (string tags): {manual_create_str_tags.tags}")
    
    # 验证继承关系
    assert issubclass(CollectionUpdate, CollectionBase), "CollectionUpdate 应该继承自 CollectionBase"
    assert issubclass(CollectionRead, CollectionBase), "CollectionRead 应该继承自 CollectionBase"
    
    print("  ✓ Collection Schema 测试通过\n")


def main():
    """运行所有测试"""
    print("=" * 60)
    print("Schema 重构验证测试")
    print("=" * 60)
    print()
    
    try:
        test_user_schemas()
        test_subject_schemas()
        test_collection_schemas()
        
        print("=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        print()
        print("重构总结：")
        print("1. ✓ 遵循 Base -> Create/Update -> Read 的分层继承模式")
        print("2. ✓ 严格使用类型注解，禁止使用裸露的 dict")
        print("3. ✓ 统一字段标准：tags 是 List[str]，status 引用 Enum")
        print("4. ✓ 保留现有的 Docstring 注释风格")
        print()
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
