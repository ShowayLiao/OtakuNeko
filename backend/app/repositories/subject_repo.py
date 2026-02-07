from typing import Dict, Any, Optional, List, Tuple
from sqlmodel import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from ..models import Subject, SubjectType, Collection
from ..schemas.subject import SubjectCreate, SubjectUpdate, SubjectUpdateList, SubjectList, SubjectUpsertList, SubjectSearchByID, SubjectSearchBase, SubjectSearchByName, SubjectWithCollection, SubjectWithCollectionList

logger = get_logger(__name__)


class SubjectRepo:
    """
    Subject 数据访问层
    封装所有与 Subject 相关的数据库操作
    """
    
    @staticmethod
    async def create(db: AsyncSession, subject_data: SubjectCreate) -> Subject:
        """
        创建新的 Subject 记录或更新现有记录（upsert 操作）
        
        Args:
            db: 数据库会话
            subject_data: Subject数据，使用 SubjectCreate schema
        
        Returns:
            创建或更新的Subject对象
        
        Raises:
            ValueError: 缺少必要的Subject ID
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlmodel import select
            from ..schemas.subject import SubjectSearchByID
            
            # 将 SubjectCreate 转换为字典
            subject_dict = subject_data.model_dump()
            
            # 检查是否已经存在相同 source 和 source_id 的 Subject
            source = subject_dict.get("source")
            source_id = subject_dict.get("source_id")
            
            search_data = SubjectSearchByID(source=source, source_id=source_id)
            result = await SubjectRepo.get_by_source(db, search_data)
            existing_subject = result[0] if result else None
            
            if existing_subject:
                # 如果存在，更新现有记录
                for field, value in subject_dict.items():
                    setattr(existing_subject, field, value)
                
                await db.commit()
                await db.refresh(existing_subject)
                
                logger.info(f"Updated existing subject: id={existing_subject.id}, source={existing_subject.source}, source_id={existing_subject.source_id}")
                return existing_subject
            else:
                # 如果不存在，创建新记录
                new_subject = Subject(**subject_dict)
                db.add(new_subject)
                await db.commit()
                await db.refresh(new_subject)
                
                logger.info(f"Created new subject: id={new_subject.id}, source={new_subject.source}, source_id={new_subject.source_id}")
                return new_subject
        except SQLAlchemyError as e:
            logger.error(f"创建/更新Subject失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_source(db: AsyncSession, search_data: SubjectSearchByID) -> Optional[SubjectWithCollection]:
        """
        根据数据源和ID查找Subject，并左外连接Collection表获取用户收藏状态
        
        Args:
            db: 数据库会话
            search_data: 搜索条件，使用 SubjectSearchByID schema
        
        Returns:
            SubjectWithCollection对象，如果Subject不存在则返回None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlalchemy import false
            
            # 构建基础查询
            query = select(Subject, Collection).outerjoin(
                Collection, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id,
                    Collection.user_id == search_data.user_id if search_data.user_id else false()
                )
            ).where(
                Subject.source == search_data.source,
                Subject.source_id == search_data.source_id
            )
            
            result = await db.execute(query)
            row = result.first()
            
            if row:
                subject, collection = row
                return SubjectWithCollection(subject=subject, collection=collection)
            else:
                return None
        except SQLAlchemyError as e:
            logger.error(f"获取Subject失败: {e}")
            raise
    
    @staticmethod
    async def search_by_name(db: AsyncSession, search_data: SubjectSearchByName) -> SubjectWithCollectionList:
        """
        根据名称搜索Subject（支持模糊匹配），并左外连接Collection表获取用户收藏状态
        
        Args:
            db: 数据库会话
            search_data: 搜索条件，使用 SubjectSearchByName schema
        
        Returns:
            SubjectWithCollectionList对象，包含条目及其关联收藏信息的列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlalchemy import false
            
            search_term = f"%{search_data.keyword}%"
            
            # 构建查询，左外连接Collection表
            query = select(Subject, Collection).outerjoin(
                Collection, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id,
                    Collection.user_id == search_data.user_id if search_data.user_id else false()
                )
            )
            
            # 构建搜索条件
            conditions = [
                Subject.name.ilike(search_term),
                Subject.name_cn.ilike(search_term),
                Subject.summary.ilike(search_term),
                Collection.comment.ilike(search_term) if Collection.comment is not None else False
            ]
            
            # 添加 JSON 字段搜索（使用PostgreSQL兼容的操作）
            from sqlalchemy import cast, String
            from sqlalchemy.dialects.postgresql import JSONB
            
            # 安全处理Collection.tags（JSON数组）
            conditions.append(
                Collection.tags.isnot(None) & 
                cast(Collection.tags, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 安全处理Subject.tags（JSON数组）
            conditions.append(
                Subject.tags.isnot(None) & 
                cast(Subject.tags, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 安全处理Subject.meta_tags（JSON数组）
            conditions.append(
                Subject.meta_tags.isnot(None) & 
                cast(Subject.meta_tags, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 安全处理Subject.infobox（JSON数组）
            conditions.append(
                Subject.infobox.isnot(None) & 
                cast(Subject.infobox, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 应用搜索条件
            query = query.where(or_(*conditions))
            
            # 应用类型过滤
            if search_data.type is not None:
                query = query.where(Subject.type == search_data.type)
            
            # 添加分页
            query = query.offset(search_data.skip).limit(search_data.limit)
            
            result = await db.execute(query)
            rows = result.all()
            
            # 转换为SubjectWithCollection对象列表
            items = []
            for subject, collection in rows:
                items.append(SubjectWithCollection(subject=subject, collection=collection))
            
            # 创建并返回SubjectWithCollectionList对象
            return SubjectWithCollectionList(total=len(items), items=items)
        except SQLAlchemyError as e:
            logger.error(f"搜索Subject失败: {e}")
            raise
    
    @staticmethod
    async def get_all(db: AsyncSession, search_data: SubjectSearchBase) -> SubjectWithCollectionList:
        """
        获取所有Subject记录，并左外连接Collection表获取用户收藏状态
        
        Args:
            db: 数据库会话
            search_data: 搜索条件，使用 SubjectSearchBase schema
        
        Returns:
            SubjectWithCollectionList对象，包含条目及其关联收藏信息的列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlalchemy import false
            
            # 构建基础查询，左外连接Collection表
            query = select(Subject, Collection).outerjoin(
                Collection, 
                and_(
                    Collection.source == Subject.source,
                    Collection.source_id == Subject.source_id,
                    Collection.user_id == search_data.user_id if search_data.user_id else false()
                )
            )
            
            # 应用过滤条件
            if search_data.type is not None:
                query = query.where(Subject.type == search_data.type)
            
            # 添加分页
            result = await db.execute(query.offset(search_data.skip).limit(search_data.limit))
            rows = result.all()
            
            # 转换为SubjectWithCollection对象列表
            items = []
            for subject, collection in rows:
                items.append(SubjectWithCollection(subject=subject, collection=collection))
            
            # 创建并返回SubjectWithCollectionList对象
            return SubjectWithCollectionList(total=len(items), items=items)
        except SQLAlchemyError as e:
            logger.error(f"获取Subject列表失败: {e}")
            raise
    
    @staticmethod
    async def count(db: AsyncSession, subject_type: Optional[int] = None) -> int:
        """
        获取Subject记录总数
        
        Args:
            db: 数据库会话
            subject_type: 可选，条目类型过滤
        
        Returns:
            Subject记录总数
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlalchemy import func
            
            query = select(func.count(Subject.id))
            
            if subject_type is not None:
                query = query.where(Subject.type == subject_type)
            
            result = await db.execute(query)
            return result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"获取Subject总数失败: {e}")
            raise
    
    @staticmethod
    async def count_by_name(db: AsyncSession, name: str) -> int:
        """
        根据名称搜索的Subject记录总数
        
        Args:
            db: 数据库会话
            name: 搜索名称
        
        Returns:
            匹配的Subject记录总数
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlalchemy import func
            
            search_term = f"%{name}%"
            # 构建搜索条件
            conditions = [
                Subject.name.ilike(search_term),
                Subject.name_cn.ilike(search_term),
                Subject.summary.ilike(search_term)
            ]
            
            # 构建查询
            query = select(func.count(Subject.id)).where(
                or_(*conditions)
            )
            
            result = await db.execute(query)
            return result.scalar_one()
        except SQLAlchemyError as e:
            logger.error(f"获取搜索Subject总数失败: {e}")
            raise
    
    @staticmethod
    async def update(db: AsyncSession, subject_data: SubjectUpdate) -> Optional[Subject]:
        """
        更新Subject信息
        
        Args:
            db: 数据库会话
            subject_data: 更新的Subject数据，使用 SubjectUpdate schema
        
        Returns:
            更新后的Subject对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from sqlalchemy import false
            
            # 验证必要的更新字段
            if not subject_data.source or not subject_data.source_id:
                logger.error("Update failed: source and source_id are required for updating subject")
                return None
            
            # 获取Subject对象，使用正确的参数类型调用get_by_source
            search_data = SubjectSearchByID(
                source=subject_data.source,
                source_id=subject_data.source_id
            )
            subject_result = await SubjectRepo.get_by_source(db, search_data)
            if not subject_result:
                logger.info(f"Subject not found for update: source={subject_data.source}, source_id={subject_data.source_id}")
                return None
            
            # 解包元组，获取Subject对象
            subject, _ = subject_result
            
            # 将 SubjectUpdate 转换为字典，只包含设置的字段
            update_data = subject_data.model_dump(exclude_unset=True)
            
            # 更新设置的字段
            for field, value in update_data.items():
                # 不允许更新source和source_id字段
                if field not in ["source", "source_id"]:
                    setattr(subject, field, value)
            
            db.add(subject)
            await db.commit()
            await db.refresh(subject)
            
            logger.info(f"Updated subject: id={subject.id}, source={subject.source}, source_id={subject.source_id}")
            return subject
        except SQLAlchemyError as e:
            logger.error(f"更新Subject失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def delete(db: AsyncSession, search_data: SubjectSearchByID) -> bool:
        """
        删除Subject
        
        Args:
            db: 数据库会话
            search_data: 搜索数据，使用 SubjectSearchByID schema
        
        Returns:
            删除成功返回True，Subject不存在返回False
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 获取Subject对象
            subject_result = await SubjectRepo.get_by_source(db, search_data)
            if not subject_result:
                return False
            
            # 解包元组，获取Subject对象
            subject, _ = subject_result
            if not subject:
                return False
            
            await db.delete(subject)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除Subject失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def batch_upsert(db: AsyncSession, data_list: SubjectUpsertList) -> int:
        """
        批量 Upsert Subject 方法
        
        Args:
            db: 数据库会话
            data_list: Subject列表，使用 SubjectUpsertList schema
        
        Returns:
            处理的条目数量
        
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
                return 0

            from app.models.subject import Subject
            
            if not data_list.items:
                return 0
            
            # 固定的唯一键字段
            unique_fields = ['source', 'source_id']
            
            # 1. 将 SubjectUpsert 对象转换为字典列表
            subject_dicts = []
            for subject_upsert in data_list.items:
                # 使用 model_dump 转换为字典，排除 unset 的字段
                subject_dict = subject_upsert.model_dump(exclude_unset=True)
                subject_dicts.append(subject_dict)
            
            if not subject_dicts:
                return 0
            
            # 2. 构建 Insert 语句
            stmt = insert(Subject).values(subject_dicts)
            
            # 3. 自动计算需要更新的字段 (除了 unique_fields 以外的所有字段)
            # 获取模型的所有列名
            all_columns = {col.name for col in Subject.__table__.columns}
            # 排除掉唯一键 (因为唯一键冲突时不用更新它自己)
            update_cols = all_columns - set(unique_fields)
            
            # 4. 构建 set_ 字典
            # 这里的 getattr(stmt.excluded, col) 是核心
            set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
            
            # 5. 添加 On Conflict 子句
            stmt = stmt.on_conflict_do_update(
                index_elements=unique_fields,
                set_=set_dict
            )
            
            # 6. 执行语句
            result = await db.execute(stmt)
            await db.commit()
            
            logger.info(f"批量 Upsert 完成: {len(subject_dicts)} 个 Subject 处理成功")
            return len(subject_dicts)
            
        except SQLAlchemyError as e:
            logger.error(f"批量 Upsert Subject 失败: {e}")
            await db.rollback()
            raise
    
    
