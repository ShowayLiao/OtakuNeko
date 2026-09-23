from datetime import datetime, timezone
from typing import Any, Optional, cast
from sqlmodel import select, and_
from sqlalchemy import desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.logging import get_logger
from ..models import Collection, Subject
from ..schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionSearchByID, 
    CollectionSearchByName, CollectionWithSubject, CollectionWithSubjectList, CollectionUpsertList
)

logger = get_logger(__name__)

# SQLModel model attributes are SQLAlchemy column descriptors at runtime, while
# their annotations describe instance values.  These aliases keep query code
# honest at that boundary without weakening the project-wide type checks.
_COLLECTION_ID = cast(Any, Collection.id)
_COLLECTION_USER_ID = cast(Any, Collection.user_id)
_COLLECTION_SOURCE = cast(Any, Collection.source)
_COLLECTION_SOURCE_ID = cast(Any, Collection.source_id)
_COLLECTION_TYPE = cast(Any, Collection.type)
_COLLECTION_UPDATED_AT = cast(Any, Collection.updated_at)
_COLLECTION_RATE = cast(Any, Collection.rate)
_COLLECTION_COMMENT = cast(Any, Collection.comment)
_COLLECTION_TAGS = cast(Any, Collection.tags)
_SUBJECT_ID = cast(Any, Subject.id)
_SUBJECT_SOURCE = cast(Any, Subject.source)
_SUBJECT_SOURCE_ID = cast(Any, Subject.source_id)
_SUBJECT_TYPE = cast(Any, Subject.type)
_SUBJECT_RATING = cast(Any, Subject.rating)
_SUBJECT_DATE = cast(Any, Subject.date)
_SUBJECT_NAME = cast(Any, Subject.name)
_SUBJECT_NAME_CN = cast(Any, Subject.name_cn)
_SUBJECT_SUMMARY = cast(Any, Subject.summary)
_SUBJECT_TAGS = cast(Any, Subject.tags)
_SUBJECT_META_TAGS = cast(Any, Subject.meta_tags)
_SUBJECT_INFOBOX = cast(Any, Subject.infobox)


class CollectionRepo:
    """
    Collection 数据访问层
    封装所有与 Collection 相关的数据库操作
    """
    
    @staticmethod
    def _is_valid_subject(subject):
        return subject is not None and subject.name and subject.name.strip()
    
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
                    _COLLECTION_SOURCE == _SUBJECT_SOURCE,
                    _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID
                )
            ).where(
                _COLLECTION_USER_ID == search_data.user_id,
                _COLLECTION_SOURCE == search_data.source,
                _COLLECTION_SOURCE_ID == search_data.source_id
            )
            
            result = await db.execute(query)
            row = result.first()
            
            if row:
                collection, subject = row
                if not CollectionRepo._is_valid_subject(subject):
                    return None
                return CollectionWithSubject(collection=collection, subject=subject)
            else:
                return None
        except SQLAlchemyError as e:
            logger.error(f"获取收藏记录失败: {e}")
            raise

    @staticmethod
    async def get_orm_by_user_and_subject(
        db: AsyncSession, user_id: int, source: str, source_id: str
    ) -> Optional[Collection]:
        """
        按 (user_id, source, source_id) 直接返回 session 绑定的 ORM 行。

        写路径必须使用本方法：CollectionWithSubject.collection 是 CollectionRead
        DTO 的副本，且 CollectionRead 没有 id 字段，写路径无法从 DTO 还原主键，
        db.add/db.delete/db.refresh 都会抛 UnmappedInstanceError。

        这里刻意不做 _is_valid_subject 校验，让写路径能够修复孤立收藏记录。

        Args:
            db: 数据库会话
            user_id: 用户ID
            source: 数据来源
            source_id: 原站ID

        Returns:
            Collection ORM 实例，不存在则返回 None

        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            query = select(Collection).where(
                _COLLECTION_USER_ID == user_id,
                _COLLECTION_SOURCE == source,
                _COLLECTION_SOURCE_ID == source_id,
            )
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取Collection ORM行失败: {e}")
            raise

    @staticmethod
    async def get_by_user(db: AsyncSession, user_id: int, subject_type: Optional[int] = None, status: Optional[int] = None, skip: int = 0, limit: Optional[int] = 100, sort_by: str = 'updated_at') -> CollectionWithSubjectList:
        """
        根据用户ID获取所有Collection，并左外连接Subject表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_type: 可选，条目类型过滤
            status: 可选，收藏状态过滤
            skip: 跳过的记录数
            limit: 返回的最大记录数
            sort_by: 排序字段
        
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
                    _COLLECTION_SOURCE == _SUBJECT_SOURCE,
                    _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID
                )
            ).where(_COLLECTION_USER_ID == user_id)
            
            # 应用条目类型过滤
            if subject_type is not None:
                # 使用 OR 条件：要么 subject 存在且类型匹配，要么 subject 不存在
                from sqlmodel import or_
                query = query.where(
                    or_(
                        (_SUBJECT_TYPE == subject_type),
                        (_SUBJECT_ID.is_(None))
                    )
                )
            
            # 应用状态过滤
            if status is not None:
                query = query.where(_COLLECTION_TYPE == status)
            
            # 应用排序
            if sort_by == 'updated_at':
                query = query.order_by(desc(_COLLECTION_UPDATED_AT))
            elif sort_by == 'rate':
                query = query.order_by(desc(_COLLECTION_RATE))
            elif sort_by == 'score':
                # 使用 rating 字段中的 score 值进行排序
                from sqlalchemy import cast, Float
                query = query.order_by(desc(cast(_SUBJECT_RATING.op('->>')('score'), Float)))
            elif sort_by == 'date':
                query = query.order_by(desc(_SUBJECT_DATE))
            
            # 保留 offset；limit=None 用于受控的内部全量画像查询。
            query = query.offset(skip)
            if limit is not None:
                query = query.limit(limit)
            
            # 执行查询
            result = await db.execute(query)
            rows = result.all()
            
            # 转换为CollectionWithSubject对象列表
            items = []
            for collection, subject in rows:
                if not CollectionRepo._is_valid_subject(subject):
                    continue
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
                if not CollectionRepo._is_valid_subject(subject):
                    continue
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
            if (
                collection_data.user_id is None
                or collection_data.source is None
                or collection_data.source_id is None
            ):
                raise ValueError(
                    "user_id, source and source_id are required to update a collection"
                )

            # 写路径必须取 ORM 行
            collection = await CollectionRepo.get_orm_by_user_and_subject(
                db,
                collection_data.user_id,
                collection_data.source,
                collection_data.source_id,
            )
            if collection is None:
                return None

            # 将 CollectionUpdate 转换为字典，只包含设置的字段
            update_data = collection_data.model_dump(exclude_unset=True)

            # 更新设置的字段
            for field, value in update_data.items():
                # 身份字段由上面的查询确定，不允许改写
                if field in ("user_id", "source", "source_id"):
                    continue
                setattr(collection, field, value)

            # GET /collections 按 updated_at 排序，编辑必须刷新时间戳
            if "updated_at" not in update_data:
                collection.updated_at = datetime.now(timezone.utc)

            await db.commit()

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
            from fastapi_cache import FastAPICache

            # 写路径必须取 ORM 行
            collection = await CollectionRepo.get_orm_by_user_and_subject(
                db, search_data.user_id, search_data.source, search_data.source_id
            )
            if collection is None:
                return False

            user_id = collection.user_id

            await db.delete(collection)
            await db.commit()
            
            # 清除用户的统计数据缓存
            await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
            logger.info(f"Cleared stats cache for user_id: {user_id}")
            
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
                    _COLLECTION_SOURCE == _SUBJECT_SOURCE,
                    _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID
                )
            )
            
            # 添加用户过滤条件
            query = query.where(_COLLECTION_USER_ID == search_data.user_id)
            
            # 添加关键词搜索条件，搜索多个字段
            if search_data.keyword:
                keyword_pattern = f"%{search_data.keyword}%"
                # 构建基本查询条件
                conditions = [
                    # Collection 表字段
                    _COLLECTION_COMMENT.ilike(keyword_pattern),
                    # Subject 表字段
                    _SUBJECT_NAME.ilike(keyword_pattern),
                    _SUBJECT_NAME_CN.ilike(keyword_pattern),
                    _SUBJECT_SUMMARY.ilike(keyword_pattern)
                ]
                
                # 添加 JSON 字段搜索（使用PostgreSQL兼容的操作）
                from sqlalchemy import cast, String
                # Collection.tags 搜索
                conditions.append(
                    _COLLECTION_TAGS.isnot(None) &
                    cast(_COLLECTION_TAGS, String).ilike(f"%{search_data.keyword}%")
                )
                # Subject.tags 搜索
                conditions.append(
                    _SUBJECT_TAGS.isnot(None) &
                    cast(_SUBJECT_TAGS, String).ilike(f"%{search_data.keyword}%")
                )
                # Subject.meta_tags 搜索
                conditions.append(
                    _SUBJECT_META_TAGS.isnot(None) &
                    cast(_SUBJECT_META_TAGS, String).ilike(f"%{search_data.keyword}%")
                )
                # Subject.infobox 搜索
                conditions.append(
                    _SUBJECT_INFOBOX.isnot(None) &
                    cast(_SUBJECT_INFOBOX, String).ilike(f"%{search_data.keyword}%")
                )
                
                query = query.where(or_(*conditions))
            
            # 应用状态过滤
            if getattr(search_data, 'status', None) is not None:
                query = query.where(_COLLECTION_TYPE == search_data.status)
            
            # 应用排序
            sort_by = getattr(search_data, 'sort_by', 'updated_at')
            if sort_by == 'updated_at':
                query = query.order_by(desc(_COLLECTION_UPDATED_AT))
            elif sort_by == 'rate':
                query = query.order_by(desc(_COLLECTION_RATE))
            elif sort_by == 'score':
                # 使用 rating 字段中的 score 值进行排序
                from sqlalchemy import cast, Float
                query = query.order_by(desc(cast(_SUBJECT_RATING.op('->>')('score'), Float)))
            elif sort_by == 'date':
                query = query.order_by(desc(_SUBJECT_DATE))
            
            # 添加分页
            query = query.offset(search_data.skip).limit(search_data.limit)
            
            # 执行查询
            result = await db.execute(query)
            rows = result.all()
            
            # 转换为CollectionWithSubject对象列表
            items = []
            for collection, subject in rows:
                if not CollectionRepo._is_valid_subject(subject):
                    continue
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
            from fastapi_cache import FastAPICache
            from ..core.config import settings
            if settings.DEPLOY_MODE == "local":
                from sqlalchemy.dialects.sqlite import insert as sqlite_insert
                insert = cast(Any, sqlite_insert)
            elif settings.DEPLOY_MODE == "cloud":
                from sqlalchemy.dialects.postgresql import insert as postgresql_insert
                insert = cast(Any, postgresql_insert)
            else:
                logger.error("Deploy mode not supported")
                return 

            if not data_list.collections:
                return

            # 固定唯一键字段
            unique_fields = ['user_id', 'source', 'source_id']
            # 唯一键与自增主键都不参与 on-conflict 更新
            non_updatable_fields = {'id', 'created_at'}

            now = datetime.now(timezone.utc)
            user_ids: set[int] = set()
            insert_rows: list[dict[str, Any]] = []
            provided_columns: set[str] = set()

            for item in data_list.collections:
                # 只有客户端显式提供的字段才参与 on-conflict 更新
                provided = item.model_dump(exclude_unset=True)

                for identity_field in unique_fields:
                    if not provided.get(identity_field):
                        raise ValueError(
                            f"Collection {identity_field} is required for upsert"
                        )
                if provided.get("type") is None:
                    # collection.type 是 NOT NULL。Core insert 不会应用模型端的
                    # Python default，而且数据库在冲突解析之前就校验 NOT NULL，
                    # 所以冲突路径也不能省掉它。
                    raise ValueError("Collection type is required for upsert")

                # 插入值使用完整 dump：所有行的 key 一致（executemany 要求），
                # 且 NOT NULL 列拿到模型默认值而不是 None。
                row = item.model_dump()
                # collection.updated_at 是 NOT NULL，Core insert 绕过了模型端的
                # default_factory，必须在 Python 侧显式物化。
                row["updated_at"] = provided.get("updated_at") or now
                insert_rows.append(row)

                provided_columns |= set(provided.keys())
                user_ids.add(row["user_id"])

            # 1. 构建 Insert 语句
            stmt = insert(Collection).values(insert_rows)

            # 2. 只更新本次显式提供的字段，避免把未提供的列清成默认值/NULL。
            #    这里必须从语句实际包含的列推导，不能用模型全部列，否则
            #    stmt.excluded.<col> 会指向语句中不存在的列。
            update_cols = (
                provided_columns | {"updated_at"}
            ) - set(unique_fields) - non_updatable_fields

            # 3. 构建 set_ 字典
            # 这里的 getattr(stmt.excluded, col) 是核心
            set_dict = {col: getattr(stmt.excluded, col) for col in sorted(update_cols)}

            # 4. 添加 On Conflict 子句
            stmt = stmt.on_conflict_do_update(
                index_elements=unique_fields,
                set_=set_dict
            )
            
            await db.execute(stmt)
            await db.commit()
            
            # 清除所有涉及用户的统计数据缓存
            for user_id in user_ids:
                await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
                logger.info(f"Cleared stats cache for user_id: {user_id}")
            
            logger.info(f"批量 Upsert 收藏记录成功，处理了 {len(data_list.collections)} 条记录")
        except SQLAlchemyError as e:
            logger.error(f"批量 Upsert 收藏记录失败: {e}")
            await db.rollback()
            raise


