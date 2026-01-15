import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from app.models import User
from app.schemas.user import UserCreate, UserUpdate
from app.services.user_service import UserService
from app.repositories.user_repo import UserRepo

# 测试数据库URL，使用内存数据库
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# 创建测试数据库引擎和会话
@pytest.fixture
async def db_session():
    """创建测试数据库会话"""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    
    # 创建所有表
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    
    # 创建会话工厂
    async_session = sessionmaker(
        engine, expire_on_commit=False, class_=AsyncSession
    )
    
    # 创建会话
    async with async_session() as session:
        yield session
    
    # 清理数据库
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)
    
    await engine.dispose()

@pytest.mark.asyncio
async def test_create_user(db_session):
    """测试创建用户功能"""
    # 创建用户数据
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        email="test@example.com",
        bangumi_id=12345,
        has_bangumi_account=True
    )
    
    # 创建用户
    created_user = await UserService.create_user(db_session, user_data)
    
    # 验证用户创建成功
    assert created_user is not None
    assert created_user.username == "testuser"
    assert created_user.nickname == "测试用户"
    assert created_user.email == "test@example.com"
    assert created_user.bangumi_id == 12345

@pytest.mark.asyncio
async def test_create_user_existing(db_session):
    """测试创建已存在的用户"""
    # 先创建一个用户
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        has_bangumi_account=False
    )
    await UserService.create_user(db_session, user_data)
    
    # 尝试创建同名用户，应该抛出异常
    with pytest.raises(ValueError, match="用户 testuser 已存在"):
        await UserService.create_user(db_session, user_data)

@pytest.mark.asyncio
async def test_get_user_by_id(db_session):
    """测试根据ID获取用户"""
    # 创建用户
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        has_bangumi_account=False
    )
    created_user = await UserService.create_user(db_session, user_data)
    
    # 根据ID获取用户
    fetched_user = await UserService.get_user_by_id(db_session, created_user.id)
    
    # 验证获取成功
    assert fetched_user is not None
    assert fetched_user.id == created_user.id
    assert fetched_user.username == created_user.username

@pytest.mark.asyncio
async def test_get_user_by_username(db_session):
    """测试根据用户名获取用户"""
    # 创建用户
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        has_bangumi_account=False
    )
    await UserService.create_user(db_session, user_data)
    
    # 根据用户名获取用户
    fetched_user = await UserService.get_user_by_username(db_session, "testuser")
    
    # 验证获取成功
    assert fetched_user is not None
    assert fetched_user.username == "testuser"

@pytest.mark.asyncio
async def test_get_user_by_bangumi_id(db_session):
    """测试根据Bangumi ID获取用户"""
    # 创建用户
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        bangumi_id=12345,
        has_bangumi_account=True
    )
    await UserService.create_user(db_session, user_data)
    
    # 根据Bangumi ID获取用户
    fetched_user = await UserService.get_user_by_bangumi_id(db_session, 12345)
    
    # 验证获取成功
    assert fetched_user is not None
    assert fetched_user.bangumi_id == 12345

@pytest.mark.asyncio
async def test_get_all_users(db_session):
    """测试获取所有用户"""
    # 创建多个用户
    for i in range(3):
        user_data = UserCreate(
            username=f"testuser{i}",
            nickname=f"测试用户{i}",
            has_bangumi_account=False
        )
        await UserService.create_user(db_session, user_data)
    
    # 获取所有用户
    users = await UserService.get_all_users(db_session)
    
    # 验证获取成功
    assert len(users) == 3

@pytest.mark.asyncio
async def test_update_user(db_session):
    """测试更新用户功能"""
    # 创建用户
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        email="old@example.com",
        has_bangumi_account=False
    )
    created_user = await UserService.create_user(db_session, user_data)
    
    # 准备更新数据
    update_data = UserUpdate(
        nickname="更新后的测试用户",
        email="new@example.com",
        sign="这是一个测试签名"
    )
    
    # 更新用户
    updated_user = await UserService.update_user(db_session, created_user.id, update_data)
    
    # 验证更新成功
    assert updated_user is not None
    assert updated_user.nickname == "更新后的测试用户"
    assert updated_user.email == "new@example.com"
    assert updated_user.sign == "这是一个测试签名"

@pytest.mark.asyncio
async def test_update_nonexistent_user(db_session):
    """测试更新不存在的用户"""
    # 准备更新数据
    update_data = UserUpdate(
        nickname="更新后的测试用户"
    )
    
    # 更新不存在的用户，应该返回None
    updated_user = await UserService.update_user(db_session, 999, update_data)
    
    # 验证返回None
    assert updated_user is None

@pytest.mark.asyncio
async def test_delete_user(db_session):
    """测试删除用户功能"""
    # 创建用户
    user_data = UserCreate(
        username="testuser",
        nickname="测试用户",
        has_bangumi_account=False
    )
    created_user = await UserService.create_user(db_session, user_data)
    
    # 删除用户
    deleted = await UserService.delete_user(db_session, created_user.id)
    
    # 验证删除成功
    assert deleted is True
    
    # 验证用户已不存在
    fetched_user = await UserService.get_user_by_id(db_session, created_user.id)
    assert fetched_user is None

@pytest.mark.asyncio
async def test_delete_nonexistent_user(db_session):
    """测试删除不存在的用户"""
    # 删除不存在的用户，应该返回False
    deleted = await UserService.delete_user(db_session, 999)
    
    # 验证返回False
    assert deleted is False

@pytest.mark.asyncio
async def test_login_user_new(db_session):
    """测试登录新用户（创建新用户）"""
    # 登录新用户
    login_user = await UserService.login_user(
        db_session,
        username="newuser",
        nickname="新登录用户",
        email="new@example.com",
        avatar_url="https://example.com/avatar.jpg",
        bangumi_id=67890,
        sign="登录测试签名"
    )
    
    # 验证登录成功并创建了新用户
    assert login_user is not None
    assert login_user.username == "newuser"
    assert login_user.nickname == "新登录用户"
    assert login_user.email == "new@example.com"
    assert login_user.avatar_url == "https://example.com/avatar.jpg"
    assert login_user.bangumi_id == 67890
    assert login_user.sign == "登录测试签名"

@pytest.mark.asyncio
async def test_login_user_existing(db_session):
    """测试登录现有用户（更新用户信息）"""
    # 先创建一个用户
    user_data = UserCreate(
        username="existinguser",
        nickname="旧昵称",
        email="old@example.com",
        has_bangumi_account=False
    )
    await UserService.create_user(db_session, user_data)
    
    # 登录现有用户并更新信息
    login_user = await UserService.login_user(
        db_session,
        username="existinguser",
        nickname="新昵称",
        email="new@example.com",
        avatar_url="https://example.com/new_avatar.jpg"
    )
    
    # 验证登录成功并更新了用户信息
    assert login_user is not None
    assert login_user.username == "existinguser"
    assert login_user.nickname == "新昵称"
    assert login_user.email == "new@example.com"
    assert login_user.avatar_url == "https://example.com/new_avatar.jpg"
