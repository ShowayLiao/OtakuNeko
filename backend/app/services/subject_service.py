from typing import Optional, List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Subject, SubjectType


async def search_subjects(
    db: AsyncSession,
    keyword: Optional[str] = None,
    subject_type: Optional[int] = None,
    limit: int = 20,
    offset: int = 0
) -> List[Subject]:
    """
    在本地数据库的所有 Subject 中搜索
    
    Args:
        db: 数据库会话
        keyword: 搜索关键词 (可选)
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        Subject 列表
    """
    # 构建查询
    query = select(Subject)
    
    # 添加过滤条件
    if keyword:
        query = query.where(Subject.name.contains(keyword) | Subject.name_cn.contains(keyword))
    
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
    subjects = result.scalars().all()
    
    return list(subjects)