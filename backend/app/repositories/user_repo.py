from typing import Optional, List
from sqlmodel import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from ..models import User
from ..schemas.user import UserCreate, UserUpdate, UserRead, UserSearch

logger = get_logger(__name__)


class UserRepo:
    """
    User 数据访问层
    封装所有与 User 相关的数据库操作
    """
    
    @staticmethod
    async def create(db: AsyncSession, user_data: UserCreate) -> User:
        """
        创建新用户
        
        Args:
            db: 数据库会话
            user_data: 用户数据，使用 UserCreate schema
        
        Returns:
            创建的User对象
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            new_user = User(**user_data.model_dump())
            db.add(new_user)
            await db.commit()
            await db.refresh(new_user)
            return new_user
        except SQLAlchemyError as e:
            logger.error(f"创建用户失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
        """
        根据ID获取用户
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            User对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_by_username(db: AsyncSession, username: str) -> Optional[User]:
        """
        根据用户名获取用户
        
        Args:
            db: 数据库会话
            username: 用户名
        
        Returns:
            User对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(User).where(User.username == username))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_by_bangumi_id(db: AsyncSession, bangumi_id: int) -> Optional[User]:
        """
        根据Bangumi ID获取用户
        
        Args:
            db: 数据库会话
            bangumi_id: Bangumi ID
        
        Returns:
            User对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(User).where(User.bangumi_id == bangumi_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """
        根据邮箱获取用户
        
        Args:
            db: 数据库会话
            email: 邮箱地址
        
        Returns:
            User对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(User).where(User.email == email))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取用户失败: {e}")
            raise
    
    @staticmethod
    async def get_all(db: AsyncSession, search_data: UserSearch) -> List[User]:
        """
        获取所有用户
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 UserSearch schema
        
        Returns:
            User对象列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(User).offset(search_data.skip).limit(search_data.limit))
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"获取用户列表失败: {e}")
            raise
    
    @staticmethod
    async def update(db: AsyncSession, user_id: int, user_data: UserUpdate) -> Optional[User]:
        """
        更新用户信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            user_data: 更新的用户数据，使用 UserUpdate schema
        
        Returns:
            更新后的User对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            user = await UserRepo.get_by_id(db, user_id)
            if not user:
                return None
            
            # 只更新设置了的字段
            update_dict = user_data.model_dump(exclude_unset=True)
            for field, value in update_dict.items():
                if hasattr(user, field):
                    setattr(user, field, value)
            
            db.add(user)
            await db.commit()
            await db.refresh(user)
            return user
        except SQLAlchemyError as e:
            logger.error(f"更新用户失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def delete(db: AsyncSession, user_id: int) -> bool:
        """
        删除用户
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            删除成功返回True，用户不存在返回False
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            user = await UserRepo.get_by_id(db, user_id)
            if not user:
                return False
            
            await db.delete(user)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除用户失败: {e}")
            await db.rollback()
            raise
