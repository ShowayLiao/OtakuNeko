from fastapi import APIRouter, Depends, HTTPException, Path, Query, UploadFile, File
from typing import Optional, List, Dict, Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.collection_service import get_my_collections, update_collection
from app.services.bangumi_service import sync_user_collections
from app.services.db_service import sync_user_collections_db
from app.schemas.collection import CollectionUpdate, CollectionOut, CollectionListResponse, CollectionItemSchema, SubjectSchema, ManualCollectionCreate
from app.models.user import User
from app.models.subject import Subject
from app.models.collection import Collection
import httpx
import json

# 缓存相关导入
from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=CollectionListResponse)
@cache(expire=60)  # 添加缓存装饰器，过期时间为60秒
async def get_my_collections_endpoint(
    username: str = Query(..., description="Bangumi用户名"),
    subject_type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/4=游戏)"),
    status: Optional[str] = Query(None, description="收藏状态 ('watching'/'completed'/'plan'/'on_hold'/'dropped')"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(20, description="分页大小，默认 20"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    sort_by: str = Query("updated_at", description="排序字段 (updated_at, rate, score, rank, date)"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        username: Bangumi用户名
        subject_type: 条目类型 (可选)
        status: 收藏状态 (可选)
        keyword: 搜索关键词 (可选)
        limit: 分页大小
        offset: 分页偏移
        sort_by: 排序字段
    
    Returns:
        包含 Subject 信息的聚合对象列表
    """
    # 根据username查询用户ID
    from app.models.user import User
    from sqlmodel import select
    
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalars().first()
    
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    
    # 状态映射：int -> str
    status_mapping_reverse = {
        3: 'watching',    # 在看
        2: 'completed',   # 看过
        1: 'plan',        # 想看
        4: 'on_hold',     # 搁置
        5: 'dropped'      # 抛弃
    }
    
    # 获取原始数据
    collections_data = await get_my_collections(
        db, user.id, status, subject_type, keyword, sort_by, limit, offset
    )
    
    # 转换为符合响应模型的格式
    items = []
    for item in collections_data["items"]:
        collection = item["collection"]
        subject = item["subject"]
        
        # 转换状态为字符串
        status_str = status_mapping_reverse.get(collection.type.value, "unknown")
        
        # 转换 datetime 为 ISO 8601 字符串
        updated_at_str = collection.updated_at.isoformat() if collection.updated_at else None
        
        # 创建CollectionItemSchema对象
        collection_item = {
            "subject_id": collection.subject_id,
            "updated_at": updated_at_str,
            "status": status_str,
            "rate": collection.rate,
            "comment": collection.comment,
            "private": collection.private,
            "tags": collection.tags,
            "subject": subject
        }
        items.append(collection_item)
    
    return {
        "total": collections_data["total"],
        "items": items
    }


@router.get("/count")
async def get_user_collection_count(
    username: str = Query(..., description="Bangumi用户名"),
    subject_type: int = Query(..., description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取指定用户、指定类型条目的收藏数量
    
    Args:
        username: Bangumi 用户名
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
        db: 数据库会话
        
    Returns:
        包含收藏数量、用户名和条目类型的字典
    """
    # 1. 查 User ID
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalars().first()
    if not user:
        return {"count": 0, "subject_type": subject_type, "username": username}

    # 2. 连表查询统计 (Collection Join Subject)
    # 逻辑: 统计 Collection 表，但条件限制在 Subject 表的 type 上
    from app.models.enums import SubjectType
    
    statement = (
        select(func.count())
        .select_from(Collection)
        .join(Subject, Collection.subject_id == Subject.id) # 显式连接
        .where(Collection.user_id == user.id)
        .where(Subject.type == SubjectType(subject_type)) # 使用枚举类型过滤
        # 可选: 如果只想统计 "看过/Collection" 的状态，可以加 .where(Collection.type == 2)
    )
    
    result = await db.execute(statement)
    count = result.scalar_one()
    
    return {"count": count, "subject_type": subject_type, "username": username}


@router.get("/{subject_id}", response_model=CollectionOut)
async def get_collection_detail(
    subject_id: int,
    username: str = Query(..., description="用户名"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取特定用户对特定条目的收藏状态
    
    Args:
        subject_id: 条目ID
        username: 用户名
        db: 数据库会话
        
    Returns:
        CollectionOut 对象
        
    Raises:
        HTTPException: 当用户不存在或收藏记录不存在时返回404
    """
    # 1. 获取 User ID
    from sqlmodel import select
    
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found")
    
    # 2. 获取 Collection
    collection_res = await db.execute(
        select(Collection).where(
            Collection.user_id == user.id,
            Collection.subject_id == subject_id
        )
    )
    collection = collection_res.scalar_one_or_none()
    
    if not collection:
        raise HTTPException(
            status_code=404,
            detail=f"Collection not found (user_id: {user.id}, subject_id: {subject_id})"
        )
    
    # 状态映射：int -> str
    status_mapping_reverse = {
        3: 'watching',    # 在看
        2: 'completed',   # 看过
        1: 'plan',        # 想看
        4: 'on_hold',     # 搁置
        5: 'dropped'      # 抛弃
    }
    
    # 转换状态为字符串
    status_str = status_mapping_reverse.get(collection.type.value, "unknown")
    
    # 转换 datetime 为 ISO 8601 字符串
    updated_at_str = collection.updated_at.isoformat() if collection.updated_at else None
    
    return {
        "subject_id": collection.subject_id,
        "status": status_str,
        "rate": collection.rate,
        "comment": collection.comment,
        "private": collection.private,
        "tags": collection.tags,
        "updated_at": updated_at_str,
        "subject": None
    }


@router.patch("/{subject_id}", response_model=CollectionOut)
async def update_collection_endpoint(
    subject_id: int = Path(..., description="条目ID"),
    update_data: CollectionUpdate = ...,
    db: AsyncSession = Depends(get_session)
):
    """
    更新用户的收藏信息
    
    Args:
        subject_id: 条目ID
        update_data: 更新数据
    
    Returns:
        更新后的 Collection 对象
    """
    # 这里应该从认证中间件获取用户ID
    # 暂时硬编码为 1，实际项目中应该替换为真实的用户ID获取逻辑
    user_id = 1
    
    updated_collection = await update_collection(
        db, user_id, subject_id, update_data
    )
    
    if not updated_collection:
        raise HTTPException(
            status_code=404,
            detail=f"收藏记录不存在 (user_id: {user_id}, subject_id: {subject_id})"
        )
    
    # 清除缓存，防止数据不一致
    try:
        await FastAPICache.clear()
    except Exception as e:
        # 缓存清除失败时，记录日志但不影响正常业务流程
        import logging
        logging.error(f"Failed to clear cache: {e}")
    
    # 状态映射：int -> str
    status_mapping_reverse = {
        3: 'watching',    # 在看
        2: 'completed',   # 看过
        1: 'plan',        # 想看
        4: 'on_hold',     # 搁置
        5: 'dropped'      # 抛弃
    }
    
    # 转换状态为字符串
    status_str = status_mapping_reverse.get(updated_collection.type.value, "unknown")
    
    # 将 Collection 对象转换为 CollectionOut 格式
    # 转换 datetime 为 ISO 8601 字符串
    updated_at_str = updated_collection.updated_at.isoformat() if updated_collection.updated_at else None
    
    return {
        "subject_id": updated_collection.subject_id,
        "status": status_str,
        "rate": updated_collection.rate,
        "comment": updated_collection.comment,
        "private": updated_collection.private,
        "tags": updated_collection.tags,
        "updated_at": updated_at_str,
        "subject": None
    }


@router.post("/sync")
async def sync_user_collections_endpoint(
    username: str = Query(..., description="Bangumi 用户名"),
    subject_type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    db: AsyncSession = Depends(get_session)
):
    """
    同步指定用户的 Bangumi 收藏数据到本地数据库
    
    Args:
        username: Bangumi 用户名
        subject_type: 可选，条目类型
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        # 调用服务层同步数据
        sync_count = await sync_user_collections(username, db, subject_type)
        
        return {
            "message": f"Successfully synced {sync_count} collections for user {username}",
            "username": username,
            "sync_count": sync_count,
            "subject_type": subject_type
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        raise HTTPException(status_code=500, detail=f"Bangumi API error: {str(e)}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/sync/douban")
async def sync_douban_collections_endpoint(
    username: str = Query(..., description="用户名"),
    file: UploadFile = File(..., description="豆瓣 JSON 文件"),
    subject_type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)。注意：仅在明确传入此参数时才会强制覆盖 JSON 中解析出的类型，否则使用 JSON 原始类型"),
    db: AsyncSession = Depends(get_session)
):
    """
    从上传的 JSON 文件导入豆瓣收藏数据到本地数据库
    
    Args:
        username: 用户名
        file: 豆瓣 JSON 文件
        subject_type: 可选的条目类型覆盖参数。如果提供，将强制覆盖所有条目的类型；如果不提供，则使用 JSON 中解析出的原始类型
        db: 数据库会话
        
    Returns:
        导入结果
    """
    try:
        print(f"[豆瓣导入] 开始处理用户 {username} 的豆瓣数据导入请求")
        
        # 验证用户名参数
        if not username or not username.strip():
            print(f"[豆瓣导入] 错误: 用户名参数缺失或为空")
            raise HTTPException(status_code=400, detail="用户名参数缺失")
        
        # 验证文件是否上传
        if not file or not file.filename:
            print(f"[豆瓣导入] 错误: 未上传文件")
            raise HTTPException(status_code=400, detail="未上传文件")
        
        print(f"[豆瓣导入] 文件名: {file.filename}, 文件大小: {file.size if hasattr(file, 'size') else '未知'}")
        
        # 读取上传的文件内容
        try:
            content = await file.read()
            print(f"[豆瓣导入] 文件读取成功，内容长度: {len(content)} 字节")
        except Exception as e:
            print(f"[豆瓣导入] 文件读取失败: {str(e)}")
            raise HTTPException(status_code=400, detail=f"文件读取失败: {str(e)}")
        
        # 解析 JSON 数据
        try:
            json_data = json.loads(content.decode('utf-8'))
            print(f"[豆瓣导入] JSON 解析成功")
        except UnicodeDecodeError as e:
            print(f"[豆瓣导入] 文件编码错误: {str(e)}")
            raise HTTPException(status_code=400, detail=f"文件编码错误，请确保文件为 UTF-8 编码: {str(e)}")
        except json.JSONDecodeError as e:
            print(f"[豆瓣导入] JSON 格式错误: {str(e)}")
            raise HTTPException(status_code=400, detail=f"JSON 格式无效: {str(e)}")
        
        # 处理不同的 JSON 结构
        try:
            if isinstance(json_data, dict) and "interest" in json_data:
                douban_items = json_data["interest"]
                print(f"[豆瓣导入] 检测到包含 'interest' 字段的字典结构，条目数量: {len(douban_items)}")
            elif isinstance(json_data, list):
                douban_items = json_data
                print(f"[豆瓣导入] 检测到列表结构，条目数量: {len(douban_items)}")
            else:
                print(f"[豆瓣导入] 无效的 JSON 结构类型: {type(json_data)}")
                raise HTTPException(status_code=400, detail="无效的 JSON 结构: 预期列表或包含 'interest' 字段的对象")
            
            if not douban_items or len(douban_items) == 0:
                print(f"[豆瓣导入] 警告: 豆瓣数据为空")
                raise HTTPException(status_code=400, detail="豆瓣数据为空，请检查导出的文件")
        except HTTPException:
            raise
        except Exception as e:
            print(f"[豆瓣导入] JSON 结构处理错误: {str(e)}")
            raise HTTPException(status_code=400, detail=f"JSON 结构处理失败: {str(e)}")
        
        # 调用服务层导入数据
        try:
            print(f"[豆瓣导入] 开始调用服务层导入数据...")
            import_count = await sync_user_collections_db(username, db, douban_items, subject_type)
            print(f"[豆瓣导入] 服务层导入完成，成功导入 {import_count} 条数据")
        except ValueError as e:
            print(f"[豆瓣导入] 数据验证错误: {str(e)}")
            raise HTTPException(status_code=400, detail=f"数据验证失败: {str(e)}")
        except Exception as e:
            print(f"[豆瓣导入] 数据库导入错误: {str(e)}")
            raise HTTPException(status_code=500, detail=f"数据库导入失败: {str(e)}")
        
        print(f"[豆瓣导入] 用户 {username} 的豆瓣数据导入成功完成")
        
        return {
            "message": f"Successfully imported {import_count} Douban items for user {username}",
            "username": username,
            "import_count": import_count
        }
    except HTTPException:
        # 重新抛出已定义的 HTTP 异常
        raise
    except Exception as e:
        # 记录完整异常信息
        import traceback
        print(f"[豆瓣导入] 未预期的异常发生:")
        print(f"[豆瓣导入] 异常类型: {type(e).__name__}")
        print(f"[豆瓣导入] 异常信息: {str(e)}")
        print(f"[豆瓣导入] 完整堆栈跟踪:")
        print(traceback.format_exc())
        
        # 返回通用服务器错误
        raise HTTPException(status_code=500, detail=f"服务器处理错误: {str(e)}")


@router.post("/manual")
async def create_manual_collection(
    data: ManualCollectionCreate,
    username: str = Query(..., description="用户名"),
    db: AsyncSession = Depends(get_session)
):
    """
    手动添加收藏
    
    Args:
        data: 手动添加的收藏数据
        username: 用户名
        db: 数据库会话
        
    Returns:
        创建成功的收藏信息
    """
    import time
    from datetime import datetime
    
    def validate_date_format(date_str: str) -> bool:
        """验证日期格式是否为 YYYY-MM-DD"""
        if not date_str:
            return True
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    
    def check_date_conflict(release_date: str, publish_date: str) -> tuple[bool, str]:
        """
        检查上映时间和发售时间是否存在冲突
        
        Args:
            release_date: 上映日期 (YYYY-MM-DD)
            publish_date: 发售日期 (YYYY-MM-DD)
            
        Returns:
            (是否有冲突, 错误信息)
        """
        if not release_date or not publish_date:
            return False, ""
        
        try:
            release_dt = datetime.strptime(release_date, "%Y-%m-%d")
            publish_dt = datetime.strptime(publish_date, "%Y-%m-%d")
            
            if release_dt > publish_dt:
                return True, "上映时间不能晚于发售时间"
            
            return False, ""
        except ValueError:
            return False, ""
    
    try:
        # 1. 验证日期格式
        if not validate_date_format(data.release_date):
            raise HTTPException(status_code=400, detail="上映日期格式错误，请使用 YYYY-MM-DD 格式")
        
        if not validate_date_format(data.publish_date):
            raise HTTPException(status_code=400, detail="发售日期格式错误，请使用 YYYY-MM-DD 格式")
        
        # 2. 检查时间冲突
        has_conflict, conflict_msg = check_date_conflict(data.release_date, data.publish_date)
        if has_conflict:
            raise HTTPException(status_code=400, detail=conflict_msg)
        
        # 3. 查询用户ID
        user_res = await db.execute(select(User).where(User.username == username))
        user = user_res.scalars().first()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        # 4. 生成唯一的source_id
        source_id = f"manual_{int(time.time() * 1000)}"
        
        # 5. 创建Subject记录
        from app.models.enums import SubjectType
        
        # 处理标签：按中文或英文逗号分割并去除空格
        tags_list = []
        if data.tags:
            tags_list = [tag.strip() for tag in data.tags.replace('，', ',').split(',') if tag.strip()]
        
        # 优先使用发售日期，如果没有则使用上映日期
        display_date = data.publish_date if data.publish_date else data.release_date
        
        subject = Subject(
            source="manual",
            source_id=source_id,
            name=data.name,
            name_cn=data.name,
            type=SubjectType(data.type),
            cover_url=data.cover_url,
            date=display_date,
            score=None,
            rank=None,
            eps=None,
            volumes=None,
            collection_total=None,
            tags=tags_list,
            meta_tags=[],
            infobox=[],
            rating_details={},
            images={}
        )
        db.add(subject)
        await db.flush()
        
        # 6. 创建Collection记录
        from app.models.enums import CollectionStatus
        collection = Collection(
            user_id=user.id,
            subject_id=subject.id,
            type=CollectionStatus(data.status),
            rate=data.rate if data.rate > 0 else None,
            comment=data.comment,
            private=False,
            tags=[],
            updated_at=datetime.now()
        )
        db.add(collection)
        
        # 7. 提交事务
        await db.commit()
        await db.refresh(subject)
        await db.refresh(collection)
        
        # 8. 清除缓存
        try:
            await FastAPICache.clear()
        except Exception as e:
            import logging
            logging.error(f"Failed to clear cache: {e}")
        
        return {
            "message": "Successfully created manual collection",
            "subject_id": subject.id,
            "user_id": user.id,
            "name": subject.name,
            "type": subject.type.value,
            "status": collection.type.value,
            "cover_url": subject.cover_url,
            "rate": collection.rate,
            "comment": collection.comment
        }
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[手动添加收藏] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create manual collection: {str(e)}")


@router.post("/batch")
async def batch_import_collections(
    items: List[Dict[str, Any]],
    username: str = Query(..., description="用户名"),
    db: AsyncSession = Depends(get_session)
):
    """
    批量导入收藏数据到本地数据库
    
    支持两种数据格式：
    1. Bangumi 官方 API 格式：直接传递 Bangumi API 返回的原始 JSON 对象
    2. 本地格式：包含 subject 和 collection 字段的条目
    
    Args:
        items: 条目列表，每个条目可以是：
              - Bangumi 官方 API 返回的原始 JSON 对象
              - 包含 subject 和 collection 的字典
        username: 用户名
        db: 数据库会话
        
    Returns:
        导入结果
    """
    try:
        from app.services.bangumi_service import upsert_subject, adapt_bangumi_subject
        from app.models.enums import CollectionStatus
        
        import_count = 0
        
        # 查询用户ID
        user_res = await db.execute(select(User).where(User.username == username))
        user = user_res.scalars().first()
        
        if not user:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        
        for item in items:
            # 判断数据格式
            if "subject" in item and "collection" in item:
                # 格式1: 本地格式 {subject: {...}, collection: {...}}
                subject_data = item["subject"]
                collection_data = item["collection"]
                
                # 使用 upsert_subject 写入 Subject
                subject = await upsert_subject(db, subject_data)
            else:
                # 格式2: Bangumi 官方 API 格式（原始 JSON 对象）
                # 使用 adapt_bangumi_subject 适配数据
                adapted_subject = adapt_bangumi_subject(item)
                
                # 使用 upsert_subject 写入 Subject
                subject = await upsert_subject(db, adapted_subject)
                
                # 从原始数据中提取收藏信息（如果有的话）
                collection_data = {}
                if "collection" in item:
                    collection_data["status"] = item["collection"].get("type", 2)
                    collection_data["rate"] = item["collection"].get("rate")
                    collection_data["comment"] = item["collection"].get("comment", "")
                    collection_data["tags"] = item["collection"].get("tags", [])
                else:
                    # 默认收藏状态
                    collection_data["status"] = 2  # completed
                    collection_data["rate"] = None
                    collection_data["comment"] = ""
                    collection_data["tags"] = []
            
            # 检查 Collection 是否已存在
            collection_res = await db.execute(
                select(Collection).where(
                    Collection.user_id == user.id,
                    Collection.subject_id == subject.id
                )
            )
            collection = collection_res.scalar_one_or_none()
            
            if not collection:
                # 创建新的 Collection
                from datetime import datetime
                collection = Collection(
                    user_id=user.id,
                    subject_id=subject.id,
                    type=CollectionStatus(collection_data.get("status", 2)),
                    rate=collection_data.get("rate"),
                    comment=collection_data.get("comment", ""),
                    private=False,
                    tags=collection_data.get("tags", []),
                    updated_at=datetime.now()
                )
                db.add(collection)
                import_count += 1
        
        await db.commit()
        
        # 清除缓存
        try:
            await FastAPICache.clear()
        except Exception as e:
            import logging
            logging.error(f"Failed to clear cache: {e}")
        
        return {
            "message": f"Successfully imported {import_count} items",
            "imported_count": import_count
        }
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[批量导入] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to import collections: {str(e)}")