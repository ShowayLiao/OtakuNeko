from typing import Dict, Any, Optional, List

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas.user import UserCreate, UserUpdate, UserRead, UserSearch, UserList, UserLogin
from app.repositories.user_repo import UserRepo
from app.core.logging import get_logger

logger = get_logger(__name__)


class UserService:
    """
    用户服务类
    封装所有与用户相关的业务逻辑
    """
    
    @staticmethod
    async def create_user(db: AsyncSession, user_data: UserCreate) -> UserRead:
        """
        创建新用户
        
        Args:
            db: 数据库会话
            user_data: 用户创建数据，使用 UserCreate schema
        
        Returns:
            创建的UserRead对象
        
        Raises:
            ValueError: 用户已存在
            Exception: 其他创建失败的异常
        """
        try:
            # 检查用户是否已存在
            existing_user = await UserRepo.get_by_username(db, user_data.username)
            if existing_user:
                raise ValueError(f"用户 {user_data.username} 已存在")
            
            # 直接使用 UserCreate schema 创建用户，不需要构造字典
            new_user = await UserRepo.create(db, user_data)
            logger.info(f"创建新用户成功: {new_user.username} (ID: {new_user.id})")
            return UserRead.model_validate(new_user)
        except ValueError as e:
            logger.error(f"创建用户失败: {e}")
            raise
        except Exception as e:
            logger.error(f"创建用户时发生未知错误: {e}")
            raise
    
    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[UserRead]:
        """
        根据ID获取用户
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            UserRead对象或None
        
        Raises:
            Exception: 查询失败的异常
        """
        try:
            user = await UserRepo.get_by_id(db, user_id)
            if user:
                logger.info(f"获取用户成功: {user.username} (ID: {user.id})")
                return UserRead.model_validate(user)
            else:
                logger.info(f"未找到用户: ID {user_id}")
                return None
        except Exception as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_user_by_username(db: AsyncSession, username: str) -> Optional[UserRead]:
        """
        根据用户名获取用户
        
        Args:
            db: 数据库会话
            username: 用户名
        
        Returns:
            UserRead对象或None
        
        Raises:
            Exception: 查询失败的异常
        """
        try:
            user = await UserRepo.get_by_username(db, username)
            if user:
                logger.info(f"获取用户成功: {user.username} (ID: {user.id})")
                return UserRead.model_validate(user)
            else:
                logger.info(f"未找到用户: {username}")
                return None
        except Exception as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_user_by_bangumi_id(db: AsyncSession, bangumi_id: int) -> Optional[UserRead]:
        """
        根据Bangumi ID获取用户
        
        Args:
            db: 数据库会话
            bangumi_id: Bangumi ID
        
        Returns:
            UserRead对象或None
        
        Raises:
            Exception: 查询失败的异常
        """
        try:
            user = await UserRepo.get_by_bangumi_id(db, bangumi_id)
            if user:
                logger.info(f"获取用户成功: {user.username} (Bangumi ID: {bangumi_id})")
                return UserRead.model_validate(user)
            else:
                logger.info(f"未找到用户: Bangumi ID {bangumi_id}")
                return None
        except Exception as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_all_users(db: AsyncSession, search_data: UserSearch) -> List[UserRead]:
        """
        获取所有用户
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 UserSearch schema
        
        Returns:
            UserRead对象列表
        
        Raises:
            Exception: 查询失败的异常
        """
        try:
            users = await UserRepo.get_all(db, search_data)
            logger.info(f"获取用户列表成功: {len(users)} 个用户")
            return [UserRead.model_validate(user) for user in users]
        except Exception as e:
            logger.error(f"获取用户列表失败: {e}")
            raise
    
    @staticmethod
    async def update_user(db: AsyncSession, user_id: int, user_data: UserUpdate) -> Optional[UserRead]:
        """
        更新用户信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            user_data: 用户更新数据，使用 UserUpdate schema
        
        Returns:
            更新后的UserRead对象或None
        
        Raises:
            Exception: 更新失败的异常
        """
        try:
            # 检查用户是否存在
            existing_user = await UserRepo.get_by_id(db, user_id)
            if not existing_user:
                logger.info(f"未找到用户: ID {user_id}")
                return None
            
            # 直接使用 UserUpdate schema 更新用户，不需要构造字典
            updated_user = await UserRepo.update(db, user_id, user_data)
            if updated_user:
                logger.info(f"更新用户成功: {updated_user.username} (ID: {updated_user.id})")
                return UserRead.model_validate(updated_user)
            return None
        except Exception as e:
            logger.error(f"更新用户失败: {e}")
            raise
    
    @staticmethod
    async def delete_user(db: AsyncSession, user_id: int) -> bool:
        """
        删除用户
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            删除成功返回True，用户不存在返回False
        
        Raises:
            Exception: 删除失败的异常
        """
        try:
            # 检查用户是否存在
            existing_user = await UserRepo.get_by_id(db, user_id)
            if not existing_user:
                logger.info(f"未找到用户: ID {user_id}")
                return False
            
            # 删除用户
            deleted = await UserRepo.delete(db, user_id)
            if deleted:
                logger.info(f"删除用户成功: {existing_user.username} (ID: {user_id})")
            return deleted
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            raise
    
    @staticmethod
    async def login_user(db: AsyncSession, login_data: UserLogin) -> UserRead:
        """
        用户登录服务
        
        流程：
        1. 获取必要的用户登录信息
        2. 调用用户查询服务检查该用户是否已存在
        3. 若用户存在，则执行更新操作
        4. 若用户不存在，则执行新增操作
        
        Args:
            db: 数据库会话
            login_data: 登录数据，使用 UserLogin schema
        
        Returns:
            登录成功的UserRead对象
        
        Raises:
            Exception: 登录失败的异常
        """
        try:
            # 检查用户是否已存在
            existing_user = await UserRepo.get_by_username(db, login_data.username)
            
            if existing_user:
                # 用户存在，执行更新操作
                logger.info(f"用户 {login_data.username} 已存在，执行更新操作")
                
                # 直接使用 UserLogin schema 转换为 UserUpdate schema
                update_data = UserUpdate(
                    avatar_url=login_data.avatar_url,
                    bangumi_id=login_data.bangumi_id,
                    bangumi_name=login_data.bangumi_name,
                    sign=login_data.sign
                )
                
                # 更新用户
                updated_user = await UserRepo.update(db, existing_user.id, update_data)
                logger.info(f"用户 {login_data.username} 登录成功，已更新用户信息")
                return UserRead.model_validate(updated_user)
            else:
                # 用户不存在，执行新增操作
                logger.info(f"用户 {login_data.username} 不存在，执行新增操作")
                
                # 直接使用 UserLogin schema 转换为 UserCreate schema
                user_data = UserCreate(
                    username=login_data.username,
                    avatar_url=login_data.avatar_url,
                    bangumi_id=login_data.bangumi_id,
                    bangumi_name=login_data.bangumi_name,
                    sign=login_data.sign
                )
                
                # 创建用户
                new_user = await UserRepo.create(db, user_data)
                logger.info(f"用户 {login_data.username} 登录成功，已创建新用户")
                return UserRead.model_validate(new_user)
        except Exception as e:
            logger.error(f"用户登录失败: {e}")
            raise
