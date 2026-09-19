from typing import Any, Optional, cast
from sqlmodel import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from ..models import Subject, Collection
from ..schemas.subject import SubjectCreate, SubjectUpdate, SubjectUpsertList, SubjectSearchByID, SubjectSearchBase, SubjectSearchByName, SubjectWithCollection, SubjectWithCollectionList

logger = get_logger(__name__)

# SQLModel exposes these attributes as SQLAlchemy InstrumentedAttribute values
# at runtime.  The model annotations intentionally remain the instance types,
# so the aliases keep query construction typed without changing behavior.
_SUBJECT_ID = cast(Any, Subject.id)
_SUBJECT_SOURCE = cast(Any, Subject.source)
_SUBJECT_SOURCE_ID = cast(Any, Subject.source_id)
_SUBJECT_NAME = cast(Any, Subject.name)
_SUBJECT_NAME_CN = cast(Any, Subject.name_cn)
_SUBJECT_SUMMARY = cast(Any, Subject.summary)
_SUBJECT_TYPE = cast(Any, Subject.type)
_SUBJECT_TAGS = cast(Any, Subject.tags)
_SUBJECT_META_TAGS = cast(Any, Subject.meta_tags)
_SUBJECT_INFOBOX = cast(Any, Subject.infobox)
_COLLECTION_SOURCE = cast(Any, Collection.source)
_COLLECTION_SOURCE_ID = cast(Any, Collection.source_id)
_COLLECTION_USER_ID = cast(Any, Collection.user_id)
_COLLECTION_COMMENT = cast(Any, Collection.comment)
_COLLECTION_TAGS = cast(Any, Collection.tags)


def _column_fill_value(model: Any, column_name: str) -> Any:
    """返回批量插入时某列缺失可用的回填值。

    NOT NULL 列不能回填 None：Core insert 会直接写出 NULL 并触发
    IntegrityError。这类列必须使用模型自身的 Python-side default；既非 nullable
    又没有默认值的列，说明调用方漏传了必填字段，应当明确报错。
    """
    column = cast(Any, model).__table__.columns.get(column_name)
    if column is None or column.nullable:
        return None
    if column.default is not None:
        default = column.default.arg
        return default() if callable(default) else default
    raise ValueError(f"{model.__name__}.{column_name} is required for batch upsert")


class SubjectRepo:
    """
    Subject 数据访问层
    封装所有与 Subject 相关的数据库操作
    """
    
    @staticmethod
    def _is_valid_subject(subject):
        return subject is not None and subject.name and subject.name.strip()
    
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
            # 将 SubjectCreate 转换为字典
            subject_dict = subject_data.model_dump()

            # Subject.last_sync 是 NOT NULL，而 SubjectCreate 的默认值是 None。
            # 显式带上 None 会让 UPDATE 分支写出 NULL，剔除后交给模型自身的
            # Python-side default 处理。
            if subject_dict.get("last_sync") is None:
                subject_dict.pop("last_sync", None)

            # 检查是否已经存在相同 source 和 source_id 的 Subject
            source = subject_dict.get("source")
            source_id = subject_dict.get("source_id")

            if not isinstance(source, str) or not isinstance(source_id, str):
                raise ValueError("source and source_id are required")

            # 写路径必须取 ORM 行，DTO 副本无法被 setattr/commit/refresh 写回
            existing_subject = await SubjectRepo.get_orm_by_source(db, source, source_id)

            if existing_subject:
                # 如果存在，更新现有记录
                for field, value in subject_dict.items():
                    setattr(existing_subject, field, value)

                await db.commit()

                logger.info(f"Updated existing subject: id={existing_subject.id}, source={existing_subject.source}, source_id={existing_subject.source_id}")
                return existing_subject
            else:
                # 如果不存在，创建新记录
                new_subject = Subject(**subject_dict)
                db.add(new_subject)
                await db.commit()

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
                    _COLLECTION_SOURCE == _SUBJECT_SOURCE,
                    _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID,
                    _COLLECTION_USER_ID == search_data.user_id if search_data.user_id else false()
                )
            ).where(
                _SUBJECT_SOURCE == search_data.source,
                _SUBJECT_SOURCE_ID == search_data.source_id
            )
            
            result = await db.execute(query)
            row = result.first()
            
            if row:
                subject, collection = row
                if not SubjectRepo._is_valid_subject(subject):
                    return None
                return SubjectWithCollection(subject=subject, collection=collection)
            else:
                return None
        except SQLAlchemyError as e:
            logger.error(f"获取Subject失败: {e}")
            raise

    @staticmethod
    async def get_orm_by_source(db: AsyncSession, source: str, source_id: str) -> Optional[Subject]:
        """
        按数据源和ID直接返回 session 绑定的 ORM 行。

        写路径必须使用本方法：SubjectWithCollection.subject 是 SubjectRead DTO
        的副本，没有 _sa_instance_state，db.add/db.delete/db.refresh 都会抛
        UnmappedInstanceError。

        与 get_by_source 不同，这里刻意不做 _is_valid_subject 校验，让写路径能够
        看到并修复/删除名称为空的脏数据行。

        Args:
            db: 数据库会话
            source: 数据来源
            source_id: 原站ID

        Returns:
            Subject ORM 实例，不存在则返回 None

        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            query = select(Subject).where(
                _SUBJECT_SOURCE == source,
                _SUBJECT_SOURCE_ID == source_id,
            )
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取Subject ORM行失败: {e}")
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
                    _COLLECTION_SOURCE == _SUBJECT_SOURCE,
                    _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID,
                    _COLLECTION_USER_ID == search_data.user_id if search_data.user_id else false()
                )
            )
            
            # 构建搜索条件
            conditions = [
                _SUBJECT_NAME.ilike(search_term),
                _SUBJECT_NAME_CN.ilike(search_term),
                _SUBJECT_SUMMARY.ilike(search_term),
                _COLLECTION_COMMENT.ilike(search_term)
            ]
            
            # 添加 JSON 字段搜索（使用PostgreSQL兼容的操作）
            from sqlalchemy import cast, String
            
            # 安全处理Collection.tags（JSON数组）
            conditions.append(
                _COLLECTION_TAGS.isnot(None) &
                cast(_COLLECTION_TAGS, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 安全处理Subject.tags（JSON数组）
            conditions.append(
                _SUBJECT_TAGS.isnot(None) &
                cast(_SUBJECT_TAGS, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 安全处理Subject.meta_tags（JSON数组）
            conditions.append(
                _SUBJECT_META_TAGS.isnot(None) &
                cast(_SUBJECT_META_TAGS, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 安全处理Subject.infobox（JSON数组）
            conditions.append(
                _SUBJECT_INFOBOX.isnot(None) &
                cast(_SUBJECT_INFOBOX, String).ilike(f"%{search_data.keyword}%")
            )
            
            # 应用搜索条件
            query = query.where(or_(*conditions))
            
            # 应用类型过滤
            if search_data.type is not None:
                query = query.where(_SUBJECT_TYPE == search_data.type)
            
            # 添加分页
            query = query.offset(search_data.skip).limit(search_data.limit)
            
            result = await db.execute(query)
            rows = result.all()
            
            # 转换为SubjectWithCollection对象列表
            items = []
            for subject, collection in rows:
                if not SubjectRepo._is_valid_subject(subject):
                    continue
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
                    _COLLECTION_SOURCE == _SUBJECT_SOURCE,
                    _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID,
                    _COLLECTION_USER_ID == search_data.user_id if search_data.user_id else false()
                )
            )
            
            # 应用过滤条件
            if search_data.type is not None:
                query = query.where(_SUBJECT_TYPE == search_data.type)
            
            # 添加分页
            result = await db.execute(query.offset(search_data.skip).limit(search_data.limit))
            rows = result.all()
            
            # 转换为SubjectWithCollection对象列表
            items = []
            for subject, collection in rows:
                if not SubjectRepo._is_valid_subject(subject):
                    continue
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
            
            query = select(func.count(_SUBJECT_ID))
            
            if subject_type is not None:
                query = query.where(_SUBJECT_TYPE == subject_type)
            
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
                _SUBJECT_NAME.ilike(search_term),
                _SUBJECT_NAME_CN.ilike(search_term),
                _SUBJECT_SUMMARY.ilike(search_term)
            ]
            
            # 构建查询
            query = select(func.count(_SUBJECT_ID)).where(
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

            # 验证必要的更新字段
            if not subject_data.source or not subject_data.source_id:
                logger.error("Update failed: source and source_id are required for updating subject")
                return None

            # 写路径必须取 ORM 行
            subject = await SubjectRepo.get_orm_by_source(
                db, subject_data.source, subject_data.source_id
            )
            if subject is None:
                logger.info(f"Subject not found for update: source={subject_data.source}, source_id={subject_data.source_id}")
                return None

            # 将 SubjectUpdate 转换为字典，只包含设置的字段
            update_data = subject_data.model_dump(exclude_unset=True)

            # 更新设置的字段
            for field, value in update_data.items():
                # 不允许更新source和source_id字段
                if field not in ["source", "source_id"]:
                    setattr(subject, field, value)

            await db.commit()

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
            # 写路径必须取 ORM 行
            subject = await SubjectRepo.get_orm_by_source(
                db, search_data.source, search_data.source_id
            )
            if subject is None:
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
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                insert = cast(Any, sqlite_insert)
            elif settings.DEPLOY_MODE == "cloud":
                from sqlalchemy.dialects.postgresql import insert as postgresql_insert
                insert = cast(Any, postgresql_insert)
            else:
                logger.error("Deploy mode not supported")
                return 0

            from app.models.subject import Subject
            from datetime import time, datetime

            if not data_list.items:
                return 0
            
            # 固定的唯一键字段
            unique_fields = ['source', 'source_id']
            
            # 1. 将 SubjectUpsert 对象转换为字典列表，并进行数据清洗
            subject_dicts = []
            logger.info(f"开始处理 {len(data_list.items)} 条数据")
            
            for i, subject_upsert in enumerate(data_list.items):
                # 使用 model_dump 转换为字典，排除 unset 的字段
                subject_dict = subject_upsert.model_dump(exclude_unset=True)
                
                # 记录每条数据的 air_time 值和类型
                if "air_time" in subject_dict:
                    val = subject_dict["air_time"]
                    # logger.info(f"第 {i} 条数据 - air_time 类型: {type(val)}, 值: {val}")
                
                # 数据清洗：移除 SQLAlchemy 字段对象，防止 "boundparameter" 错误
                # 强制清洗 air_time
                if "air_time" in subject_dict:
                    val = subject_dict["air_time"]
                    # 如果不是 time、datetime 或 str 对象且不是 None，强制置空
                    if val is not None and not isinstance(val, (time, datetime, str)):
                        logger.warning(f"清洗非法 air_time 数据 (第 {i} 条): {val} (类型: {type(val)}) -> None")
                        subject_dict["air_time"] = None
                
                # 强制清洗 date（对应 air_date）
                if "date" in subject_dict:
                    val = subject_dict["date"]
                    # 确保 date 是字符串或 None
                    if val is not None and not isinstance(val, str):
                        logger.warning(f"清洗非法 date 数据 (第 {i} 条): {val} (类型: {type(val)}) -> None")
                        subject_dict["date"] = None
                
                subject_dicts.append(subject_dict)
            
            if not subject_dicts:
                return 0

            # ================= [修复的核心代码] 开始 =================
            # 2. 统一所有字典的结构
            # SQLAlchemy 批量插入要求所有字典的 key 必须一致。
            # 由于使用了 exclude_unset=True，不同对象的 key 可能不同，这会导致 explicitly rendered as a boundparameter 错误。
            
            # 获取所有字典中出现过的所有 key 的并集
            all_keys = set().union(*(d.keys() for d in subject_dicts))
            
            # 回填缺失的 key：nullable 列回填 None，NOT NULL 列必须用模型默认值，
            # 否则异构批次会写出 NULL 并触发 IntegrityError。
            missing_keys = {k for d in subject_dicts for k in all_keys if k not in d}
            fill_values = {k: _column_fill_value(Subject, k) for k in missing_keys}
            for d in subject_dicts:
                for k in all_keys:
                    if k not in d:
                        d[k] = fill_values[k]
            
            logger.info(f"数据清洗与结构统一完成，共处理 {len(subject_dicts)} 条数据")
            # ================= [修复的核心代码] 结束 =================
            
            # 3. 构建 Insert 语句
            stmt = insert(Subject).values(subject_dicts)
            
            # 4. 自动计算需要更新的字段 (除了 unique_fields 以外的所有字段)
            # 仅更新本次数据中包含的字段 (all_keys)，避免更新那些完全没有传的字段
            # 同时排除 created_at 和 id 等不应更新的字段
            non_updatable_fields = {'id', 'created_at'}
            update_cols = all_keys - set(unique_fields) - non_updatable_fields
            
            # 5. 构建 set_ 字典
            set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
            
            # 6. 添加 On Conflict 子句
            if set_dict:
                stmt = stmt.on_conflict_do_update(
                    index_elements=unique_fields,
                    set_=set_dict
                )
            else:
                # 如果没有需要更新的字段，则 Do Nothing
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=unique_fields
                )
            
            # 7. 执行语句
            await db.execute(stmt)
            await db.commit()
            
            # 清除可能受影响的用户统计缓存
            try:
                from fastapi_cache import FastAPICache
                from sqlalchemy import select, and_
                
                # 收集所有与这些 Subject 相关的用户 ID
                affected_user_ids = set()
                # 优化：只需要遍历 unique_keys 即可查询
                for item_dict in subject_dicts:
                    source = item_dict.get('source')
                    source_id = item_dict.get('source_id')
                    
                    if not source or not source_id:
                        continue

                    # 查询与当前 Subject 相关的所有收藏记录
                    subject_query = select(_COLLECTION_USER_ID).where(
                        and_(
                            _COLLECTION_SOURCE == source,
                            _COLLECTION_SOURCE_ID == source_id
                        )
                    )
                    subject_result = await db.execute(subject_query)
                    for user_id, in subject_result.all():
                        affected_user_ids.add(user_id)
                
                # 清空每个受影响用户的统计缓存
                for user_id in affected_user_ids:
                    await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
                    logger.info(f"Cleared stats cache for user_id: {user_id} due to subject update")
            except Exception as e:
                logger.error(f"Failed to clear stats cache: {e}")
            
            logger.info(f"批量 Upsert 完成: {len(subject_dicts)} 个 Subject 处理成功")
            return len(subject_dicts)
            
        except SQLAlchemyError as e:
            logger.error(f"批量 Upsert Subject 失败: {e}")
            await db.rollback()
            raise
    
    
