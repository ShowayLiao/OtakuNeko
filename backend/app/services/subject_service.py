import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_

from app.models import Collection, Subject, SubjectType, User
from app.schemas.collection import CollectionRead
from app.schemas.subject import SubjectWithUserStatus
from app.services.bangumi_client import search_subjects as search_bangumi_subjects
from app.schemas.adapters import adapt_bangumi_subject
from app.repositories.subject_repo import SubjectRepo

logger = logging.getLogger(__name__)


async def create_subject(
    db: AsyncSession,
    subject_data: Dict[str, Any],
    source: str = "bangumi",
    source_id: Optional[str] = None
) -> Subject:
    """
    创建新条目
    
    Args:
        db: 数据库会话
        subject_data: 条目数据
        source: 数据源
        source_id: 原站ID
    
    Returns:
        创建的Subject对象
    """
    try:
        new_subject = await SubjectRepo.create(db, subject_data, source, source_id)
        logger.info(f"创建新条目成功: {new_subject.name} (ID: {new_subject.id})")
        return new_subject
    except Exception as e:
        logger.error(f"创建条目失败: {e}")
        raise


async def get_subject_by_id(
    db: AsyncSession,
    subject_id: int,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    根据ID获取条目
    
    Args:
        db: 数据库会话
        subject_id: 条目ID
        user_id: 用户ID，用于查询收藏状态
    
    Returns:
        包含条目信息和收藏状态的字典
    """
    try:
        subject = await SubjectRepo.get_by_id(db, subject_id)
        if not subject:
            return None
        
        # 构造返回数据
        item_dict = SubjectWithUserStatus.model_validate(subject).model_dump()
        
        # 检查收藏状态
        if user_id:
            from app.repositories.collection_repo import CollectionRepo
            collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject_id)
            if collection:
                item_dict["is_collected"] = True
                collection_info = CollectionRead(
                    subject_id=collection.subject_id,
                    updated_at=collection.updated_at,
                    status=collection.type,
                    rate=collection.rate,
                    comment=collection.comment,
                    private=collection.private,
                    tags=collection.tags or [],
                    subject=None
                )
                item_dict["collection_info"] = collection_info.model_dump()
            else:
                item_dict["is_collected"] = False
                item_dict["collection_info"] = None
        else:
            item_dict["is_collected"] = False
            item_dict["collection_info"] = None
        
        return item_dict
    except Exception as e:
        logger.error(f"获取条目失败: {e}")
        raise


async def get_subject_by_source(
    db: AsyncSession,
    source: str,
    source_id: str,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    根据数据源和ID获取条目
    
    Args:
        db: 数据库会话
        source: 数据源
        source_id: 原站ID
        user_id: 用户ID，用于查询收藏状态
    
    Returns:
        包含条目信息和收藏状态的字典
    """
    try:
        subject = await SubjectRepo.get_by_source(db, source, source_id)
        if not subject:
            return None
        
        # 构造返回数据
        item_dict = SubjectWithUserStatus.model_validate(subject).model_dump()
        
        # 检查收藏状态
        if user_id:
            from app.repositories.collection_repo import CollectionRepo
            collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject.id)
            if collection:
                item_dict["is_collected"] = True
                collection_info = CollectionRead(
                    subject_id=collection.subject_id,
                    updated_at=collection.updated_at,
                    status=collection.type,
                    rate=collection.rate,
                    comment=collection.comment,
                    private=collection.private,
                    tags=collection.tags or [],
                    subject=None
                )
                item_dict["collection_info"] = collection_info.model_dump()
            else:
                item_dict["is_collected"] = False
                item_dict["collection_info"] = None
        else:
            item_dict["is_collected"] = False
            item_dict["collection_info"] = None
        
        return item_dict
    except Exception as e:
        logger.error(f"获取条目失败: {e}")
        raise


async def update_subject(
    db: AsyncSession,
    subject_id: int,
    subject_data: Dict[str, Any]
) -> Optional[Subject]:
    """
    更新条目
    
    Args:
        db: 数据库会话
        subject_id: 条目ID
        subject_data: 更新的条目数据
    
    Returns:
        更新后的Subject对象或None
    """
    try:
        updated_subject = await SubjectRepo.update(db, subject_id, subject_data)
        if updated_subject:
            logger.info(f"更新条目成功: {updated_subject.name} (ID: {updated_subject.id})")
        return updated_subject
    except Exception as e:
        logger.error(f"更新条目失败: {e}")
        raise


async def delete_subject(
    db: AsyncSession,
    subject_id: int
) -> bool:
    """
    删除条目
    
    Args:
        db: 数据库会话
        subject_id: 条目ID
    
    Returns:
        删除成功返回True，条目不存在返回False
    """
    try:
        deleted = await SubjectRepo.delete(db, subject_id)
        if deleted:
            logger.info(f"删除条目成功: ID {subject_id}")
        return deleted
    except Exception as e:
        logger.error(f"删除条目失败: {e}")
        raise


async def get_all_subjects(
    db: AsyncSession,
    skip: int = 0,
    limit: int = 100,
    subject_type: Optional[int] = None,
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    获取所有条目
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的最大记录数
        subject_type: 可选，条目类型过滤
        user_id: 用户ID，用于查询收藏状态
    
    Returns:
        包含条目信息和收藏状态的字典列表
    """
    try:
        subjects = await SubjectRepo.get_all(db, skip, limit, subject_type)
        
        # 构造返回数据
        final_list = []
        for subject in subjects:
            item_dict = SubjectWithUserStatus.model_validate(subject).model_dump()
            
            # 检查收藏状态
            if user_id:
                from app.repositories.collection_repo import CollectionRepo
                collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject.id)
                if collection:
                    item_dict["is_collected"] = True
                    collection_info = CollectionRead(
                        subject_id=collection.subject_id,
                        updated_at=collection.updated_at,
                        status=collection.type,
                        rate=collection.rate,
                        comment=collection.comment,
                        private=collection.private,
                        tags=collection.tags or [],
                        subject=None
                    )
                    item_dict["collection_info"] = collection_info.model_dump()
                else:
                    item_dict["is_collected"] = False
                    item_dict["collection_info"] = None
            else:
                item_dict["is_collected"] = False
                item_dict["collection_info"] = None
            
            final_list.append(item_dict)
        
        return final_list
    except Exception as e:
        logger.error(f"获取条目列表失败: {e}")
        raise


async def search_subject_by_id(
    db: AsyncSession,
    subject_id: int,
    user_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    基于ID的精确搜索
    
    Args:
        db: 数据库会话
        subject_id: 条目ID
        user_id: 用户ID，用于查询收藏状态
    
    Returns:
        包含条目信息和收藏状态的字典
    """
    return await get_subject_by_id(db, subject_id, user_id)


async def search_subject_by_name(
    db: AsyncSession,
    name: str,
    skip: int = 0,
    limit: int = 20,
    user_id: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    基于名称的宽泛搜索
    
    Args:
        db: 数据库会话
        name: 搜索名称
        skip: 跳过的记录数
        limit: 返回的最大记录数
        user_id: 用户ID，用于查询收藏状态
    
    Returns:
        包含条目信息和收藏状态的字典列表
    """
    try:
        subjects = await SubjectRepo.search_by_name(db, name, skip, limit)
        
        # 构造返回数据
        final_list = []
        for subject in subjects:
            item_dict = SubjectWithUserStatus.model_validate(subject).model_dump()
            
            # 检查收藏状态
            if user_id:
                from app.repositories.collection_repo import CollectionRepo
                collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject.id)
                if collection:
                    item_dict["is_collected"] = True
                    collection_info = CollectionRead(
                        subject_id=collection.subject_id,
                        updated_at=collection.updated_at,
                        status=collection.type,
                        rate=collection.rate,
                        comment=collection.comment,
                        private=collection.private,
                        tags=collection.tags or [],
                        subject=None
                    )
                    item_dict["collection_info"] = collection_info.model_dump()
                else:
                    item_dict["is_collected"] = False
                    item_dict["collection_info"] = None
            else:
                item_dict["is_collected"] = False
                item_dict["collection_info"] = None
            
            final_list.append(item_dict)
        
        return final_list
    except Exception as e:
        logger.error(f"搜索条目失败: {e}")
        raise


async def search_subject_cloud(
    db: AsyncSession,
    keyword: Optional[str] = None,
    subject_type: Optional[int] = None,
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    """
    调用 Bangumi API 进行搜索
    
    Args:
        db: 数据库会话
        keyword: 搜索关键词
        subject_type: 条目类型
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        包含搜索结果和来源信息的字典
    """
    try:
        logger.info(f"从 Bangumi API 搜索: {keyword}")
        remote_response = await search_bangumi_subjects(keyword, subject_type, limit, offset)
        
        # 提取数据列表
        remote_data_list = remote_response.get("data", [])
        
        if not remote_data_list:
            return {
                "data": [],
                "source": "remote",
                "total": 0
            }
        
        # 使用适配器模式转换数据格式
        adapted_results = []
        for bangumi_data in remote_data_list:
            try:
                adapted_data = adapt_bangumi_subject(bangumi_data)
                # 远程搜索的数据默认未收藏
                adapted_data["is_collected"] = False
                adapted_data["collection_info"] = None
                adapted_results.append(adapted_data)
            except Exception as e:
                logger.error(f"适配 Bangumi 数据失败: {e}, 数据: {bangumi_data}")
                continue
        
        return {
            "data": adapted_results,
            "source": "remote",
            "total": len(adapted_results)
        }
        
    except Exception as e:
        logger.error(f"远程搜索失败: {e}")
        # 返回空结果
        return {
            "data": [],
            "source": "remote",
            "total": 0,
            "error": str(e)
        }


async def search_subjects(
    db: AsyncSession,
    keyword: Optional[str] = None,
    subject_type: Optional[int] = None,
    user_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    在本地数据库的所有 Subject 中搜索
    
    Args:
        db: 数据库会话
        keyword: 搜索关键词 (可选)
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        user_id: 用户ID，用于查询收藏状态 (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        SubjectWithUserStatus 字典列表
    """
    # 构建查询，使用 LEFT JOIN 获取收藏状态
    if user_id:
        query = select(Subject, Collection).outerjoin(
            Collection,
            (Collection.subject_id == Subject.id) & (Collection.user_id == user_id)
        )
    else:
        query = select(Subject)
    
    # 添加过滤条件
    if keyword:
        # 使用 ilike 实现大小写不敏感的模糊搜索，同时在 name 和 name_cn 字段中匹配
        query = query.where(
            or_(
                Subject.name.ilike(f"%{keyword}%"),
                Subject.name_cn.ilike(f"%{keyword}%")
            )
        )
    
    if subject_type:
        try:
            # 验证 subject_type 是否有效
            subject_type_enum = SubjectType(subject_type)
            query = query.where(Subject.type == subject_type_enum)
        except ValueError:
            # 如果类型无效，返回空列表
            return []
    
    # 添加分页
    query = query.limit(limit).offset(offset)
    
    # 执行查询
    result = await db.execute(query)
    rows = result.all()
    
    # 构造结果列表
    final_list = []
    for row in rows:
        if user_id:
            subject, collection = row
        else:
            subject = row[0] if isinstance(row, tuple) else row
            collection = None
        
        # 从 Subject 对象构造基础数据
        item_dict = SubjectWithUserStatus.model_validate(subject).model_dump()
        
        # 检查是否已收藏
        if collection:
            item_dict["is_collected"] = True
            # 构造收藏信息
            collection_info = CollectionRead(
                subject_id=collection.subject_id,
                updated_at=collection.updated_at,
                status=collection.type,
                rate=collection.rate,
                comment=collection.comment,
                private=collection.private,
                tags=collection.tags or [],
                subject=None
            )
            item_dict["collection_info"] = collection_info.model_dump()
        else:
            item_dict["is_collected"] = False
            item_dict["collection_info"] = None
        
        final_list.append(item_dict)
    
    return final_list


async def search_mixed(
    db: AsyncSession,
    keyword: Optional[str] = None,
    subject_type: Optional[int] = None,
    user_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    """
    混合搜索服务：本地优先，远程回退
    
    实现策略：
    1. Step 1 (Local): 使用 SQL LIKE 查询本地 Subject 表，同时查询用户收藏状态
    2. Step 2 (Remote Check): 如果本地结果数量为 0，则调用 Bangumi API
    3. Step 3 (Adaptation): 如果数据来自 Remote，使用适配器模式转换为统一格式，但不入库
    
    Args:
        db: 数据库会话
        keyword: 搜索关键词
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        user_id: 用户ID，用于查询收藏状态 (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        包含搜索结果和来源信息的字典：
        {
            "data": List[Dict],  # 统一格式的条目数据 (SubjectWithUserStatus)
            "source": "local" | "remote",  # 数据来源
            "total": int  # 总数
        }
    """
    # Step 1: 本地搜索
    local_results = await search_subjects(db, keyword, subject_type, user_id, limit, offset)
    
    if local_results:
        # 本地有结果，返回本地数据
        return {
            "data": local_results,
            "source": "local",
            "total": len(local_results)
        }
    
    # Step 2: 本地无结果，尝试远程搜索
    return await search_subject_cloud(db, keyword, subject_type, limit, offset)