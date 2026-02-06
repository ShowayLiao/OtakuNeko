from typing import Dict, Any, Optional, List, Tuple
import logging
from datetime import datetime
from sqlmodel import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ..models import Collection, CollectionStatus, Subject
from ..schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionSearchByID, 
    CollectionSearchBase, CollectionSearchByName, CollectionUpdateList, CollectionList, CollectionCreateList,
    CollectionWithSubject, CollectionWithSubjectList, CollectionUpsertList
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
    async def get_by_user_and_subject(db: AsyncSession, search_data: CollectionSearchByID) -> Optional[CollectionWithSubject]:
        """
        根据用户ID和条目ID获取Collection，并左外连接Subject表
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 CollectionSearchByID schema
        
        Returns:
            CollectionWithSubject对象，如果Collection不存在则返回None
        
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
                return CollectionWithSubject(collection=collection, subject=subject)
            else:
                return None
        except SQLAlchemyError as e:
            logger.error(f"获取收藏记录失败: {e}")
            raise
    
    @staticmethod
    async def get_by_user(db: AsyncSession, user_id: int, subject_type: Optional[int] = None, skip: int = 0, limit: int = 100) -> CollectionWithSubjectList:
        """
        根据用户ID获取所有Collection，并左外连接Subject表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_type: 可选，条目类型过滤
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            CollectionWithSubjectList对象，包含收藏及其关联条目信息的列表
        
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
            rows = result.all()
            
            # 转换为CollectionWithSubject对象列表
            items = []
            for collection, subject in rows:
                items.append(CollectionWithSubject(collection=collection, subject=subject))
            
            # 创建并返回CollectionWithSubjectList对象
            return CollectionWithSubjectList(total=len(items), items=items)
        except SQLAlchemyError as e:
            logger.error(f"获取用户收藏列表失败: {e}")
            raise
    
    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> CollectionWithSubjectList:
        """
        获取所有Collection记录，并左外连接Subject表
        
        Args:
            db: 数据库会话
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            CollectionWithSubjectList对象，包含收藏及其关联条目信息的列表
        
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
            rows = result.all()
            
            # 转换为CollectionWithSubject对象列表
            items = []
            for collection, subject in rows:
                items.append(CollectionWithSubject(collection=collection, subject=subject))
            
            # 创建并返回CollectionWithSubjectList对象
            return CollectionWithSubjectList(total=len(items), items=items)
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
    ) -> CollectionWithSubjectList:
        """
        根据关键词搜索收藏记录，并左外连接Subject表获取关联条目
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 CollectionSearchByName schema
        
        Returns:
            CollectionWithSubjectList对象，包含收藏及其关联条目信息的列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlmodel import or_
            from app.schemas.collection import CollectionWithSubjectList
            from app.schemas.collection import CollectionWithSubject
            
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
            
            # 添加关键词搜索条件，搜索多个字段
            if search_data.keyword:
                keyword_pattern = f"%{search_data.keyword}%"
                # 构建基本查询条件
                conditions = [
                    # Collection 表字段
                    Collection.comment.ilike(keyword_pattern) if Collection.comment is not None else False,
                    # Subject 表字段
                    Subject.name.ilike(keyword_pattern) if Subject.name is not None else False,
                    Subject.name_cn.ilike(keyword_pattern) if Subject.name_cn is not None else False,
                    Subject.summary.ilike(keyword_pattern) if Subject.summary is not None else False
                ]
                
                # 添加 JSON 字段搜索（使用PostgreSQL兼容的操作）
                from sqlalchemy import cast, String
                # Collection.tags 搜索
                conditions.append(
                    Collection.tags.isnot(None) & 
                    cast(Collection.tags, String).ilike(f"%{search_data.keyword}%")
                )
                # Subject.tags 搜索
                conditions.append(
                    Subject.tags.isnot(None) & 
                    cast(Subject.tags, String).ilike(f"%{search_data.keyword}%")
                )
                # Subject.meta_tags 搜索
                conditions.append(
                    Subject.meta_tags.isnot(None) & 
                    cast(Subject.meta_tags, String).ilike(f"%{search_data.keyword}%")
                )
                # Subject.infobox 搜索
                conditions.append(
                    Subject.infobox.isnot(None) & 
                    cast(Subject.infobox, String).ilike(f"%{search_data.keyword}%")
                )
                
                query = query.where(or_(*conditions))
            
            # 添加分页
            query = query.offset(search_data.skip).limit(search_data.limit)
            
            # 执行查询
            result = await db.execute(query)
            rows = result.all()
            
            # 转换为CollectionWithSubject对象列表
            items = []
            for collection, subject in rows:
                items.append(CollectionWithSubject(
                    collection=collection,
                    subject=subject
                ))
            
            # 创建并返回CollectionWithSubjectList对象
            return CollectionWithSubjectList(
                total=len(items),
                items=items
            )
        except SQLAlchemyError as e:
            logger.error(f"搜索收藏记录失败: {e}")
            raise
    
    @staticmethod
    async def batch_upsert(db: AsyncSession, data_list: CollectionUpsertList) -> None:
        """
        批量 Upsert 收藏记录
        
        Args:
            db: 数据库会话
            data_list: 收藏列表数据，使用 CollectionUpsertList schema
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from ..core.config import settings
            if settings.DEPLOY_MODE == "local":
                from sqlalchemy.dialects.sqlite import insert
            elif settings.DEPLOY_MODE == "cloud":
                from sqlalchemy.dialects.postgresql import insert
            else:
                logging.error("Deploy mode not supported")
                return 

            if not data_list.collections:
                return
            
            # 固定唯一键字段
            unique_fields = ['user_id', 'source', 'source_id']
            
            # 准备数据列表
            items_data = [item.model_dump() for item in data_list.collections]
            
            # 1. 构建 Insert 语句
            stmt = insert(Collection).values(items_data)
            
            # 2. 自动计算需要更新的字段 (除了 unique_fields 以外的所有字段)
            # 获取模型的所有列名
            all_columns = {col.name for col in Collection.__table__.columns}
            # 排除掉唯一键 (因为唯一键冲突时不用更新它自己)
            update_cols = all_columns - set(unique_fields)
            
            # 3. 构建 set_ 字典
            # 这里的 getattr(stmt.excluded, col) 是核心
            set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
            
            # 4. 添加 On Conflict 子句
            stmt = stmt.on_conflict_do_update(
                index_elements=unique_fields,
                set_=set_dict
            )
            
            await db.execute(stmt)
            await db.commit()
            
            logger.info(f"批量 Upsert 收藏记录成功，处理了 {len(data_list.collections)} 条记录")
        except SQLAlchemyError as e:
            logger.error(f"批量 Upsert 收藏记录失败: {e}")
            await db.rollback()
            raise


