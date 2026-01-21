from typing import Dict, Any, Optional, List, Tuple
import logging
from datetime import datetime
from sqlmodel import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ..models import Collection, CollectionStatus, Subject
from ..schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionSearchByID, 
    CollectionSearchBase, CollectionSearchByName
)

logger = logging.getLogger(__name__)


class CollectionRepo:
    """
    Collection 数据访问层
    封装所有与 Collection 相关的数据库操作
    """
    
    @staticmethod
    async def create(db: AsyncSession, collection_data: CollectionCreate) -> Collection:
        """
        创建新的 Collection 记录
        
        Args:
            db: 数据库会话
            collection_data: 收藏数据，使用 CollectionCreate schema
        
        Returns:
            创建的Collection对象
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 直接使用 schema 数据创建 Collection 对象
            new_collection = Collection(**collection_data.model_dump())
            db.add(new_collection)
            await db.commit()
            await db.refresh(new_collection)
            
            logger.info(f"Created collection: user_id={new_collection.user_id}, source={new_collection.source}, source_id={new_collection.source_id}")
            return new_collection
        except SQLAlchemyError as e:
            logger.error(f"创建收藏记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_user_and_subject(db: AsyncSession, search_data: CollectionSearchByID) -> Optional[Tuple[Collection, Optional[Subject]]]:
        """
        根据用户ID和条目ID获取Collection，并左外连接Subject表
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 CollectionSearchByID schema
        
        Returns:
            (Collection对象, Subject对象)元组，如果Collection不存在则返回None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 构建查询，左外连接Subject表
            query = select(Collection, Subject).outerjoin(
                Subject, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id
                )
            ).where(
                Collection.user_id == search_data.user_id,
                Collection.source == search_data.source,
                Collection.source_id == search_data.source_id
            )
            
            result = await db.execute(query)
            row = result.first()
            
            if row:
                collection, subject = row
                return (collection, subject)
            else:
                return None
        except SQLAlchemyError as e:
            logger.error(f"获取收藏记录失败: {e}")
            raise
    
    @staticmethod
    async def get_by_user(db: AsyncSession, user_id: int, subject_type: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Tuple[Collection, Optional[Subject]]]:
        """
        根据用户ID获取所有Collection，并左外连接Subject表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_type: 可选，条目类型过滤
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            包含(Collection对象, Subject对象)元组的列表，Subject可能为None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 构建查询，左外连接Subject表
            query = select(Collection, Subject).outerjoin(
                Subject, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id
                )
            ).where(Collection.user_id == user_id)
            
            # 应用条目类型过滤
            if subject_type is not None:
                # 使用 OR 条件：要么 subject 存在且类型匹配，要么 subject 不存在
                from sqlmodel import or_
                query = query.where(
                    or_(
                        (Subject.type == subject_type),
                        (Subject.id.is_(None))
                    )
                )
            
            # 添加分页
            query = query.offset(skip).limit(limit)
            
            # 执行查询
            result = await db.execute(query)
            return list(result.all())
        except SQLAlchemyError as e:
            logger.error(f"获取用户收藏列表失败: {e}")
            raise
    
    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Tuple[Collection, Optional[Subject]]]:
        """
        获取所有Collection记录，并左外连接Subject表
        
        Args:
            db: 数据库会话
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            包含(Collection对象, Subject对象)元组的列表，Subject可能为None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 构建查询，左外连接Subject表
            query = select(Collection, Subject).outerjoin(
                Subject, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id
                )
            )
            
            # 添加分页
            query = query.offset(skip).limit(limit)
            
            # 执行查询
            result = await db.execute(query)
            return list(result.all())
        except SQLAlchemyError as e:
            logger.error(f"获取收藏列表失败: {e}")
            raise
    
    @staticmethod
    async def update(db: AsyncSession, collection_data: CollectionUpdate) -> Optional[Collection]:
        """
        更新 Collection 记录
        
        Args:
            db: 数据库会话
            collection_data: 更新的收藏数据，使用 CollectionUpdate schema
        
        Returns:
            更新后的Collection对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 从 collection_data 中提取搜索信息
            search_data = CollectionSearchByID(
                user_id=collection_data.user_id,
                source=collection_data.source,
                source_id=collection_data.source_id
            )
            
            # 获取Collection对象
            result = await CollectionRepo.get_by_user_and_subject(db, search_data)
            if not result:
                return None
            
            # 解包元组，获取Collection对象
            collection, _ = result
            
            # 将 CollectionUpdate 转换为字典，只包含设置的字段
            update_data = collection_data.model_dump(exclude_unset=True)
            
            # 更新设置的字段
            for field, value in update_data.items():
                setattr(collection, field, value)
            
            # 保存更新
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            
            logger.info(f"Updated collection: user_id={collection.user_id}, source={collection.source}, source_id={collection.source_id}")
            return collection
        except SQLAlchemyError as e:
            logger.error(f"更新收藏记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def delete(db: AsyncSession, search_data: CollectionSearchByID) -> bool:
        """
        删除 Collection 记录
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 CollectionSearchByID schema
        
        Returns:
            删除成功返回True，收藏记录不存在返回False
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await CollectionRepo.get_by_user_and_subject(db, search_data)
            if not result:
                return False
            
            # 解包元组，获取Collection对象
            collection, _ = result
            
            await db.delete(collection)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除收藏记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def search_by_keyword(
        db: AsyncSession,
        search_data: CollectionSearchByName
    ) -> List[Tuple[Collection, Optional[Subject]]]:
        """
        根据关键词搜索收藏记录，并左外连接Subject表获取关联条目
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 CollectionSearchByName schema
        
        Returns:
            包含(Collection对象, Subject对象)元组的列表，Subject可能为None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlmodel import or_
            
            # 构建查询，左外连接Subject表
            query = select(Collection, Subject).outerjoin(
                Subject, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id
                )
            )
            
            # 添加用户过滤条件
            query = query.where(Collection.user_id == search_data.user_id)
            
            # 添加关键词搜索条件，搜索 name、name_cn 和 comment 字段
            if search_data.keyword:
                query = query.where(
                    or_(
                        Collection.name.ilike(f"%{search_data.keyword}%"),
                        Collection.name_cn.ilike(f"%{search_data.keyword}%"),
                        Collection.comment.ilike(f"%{search_data.keyword}%"),
                        Subject.name.ilike(f"%{search_data.keyword}%"),
                        Subject.name_cn.ilike(f"%{search_data.keyword}%")
                    )
                )
            
            # 添加分页
            query = query.offset(search_data.skip).limit(search_data.limit)
            
            # 执行查询并直接返回结果
            result = await db.execute(query)
            return list(result.all())
        except SQLAlchemyError as e:
            logger.error(f"搜索收藏记录失败: {e}")
            raise
    
    