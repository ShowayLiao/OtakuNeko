from typing import Dict, Any, Optional, List
import logging
from sqlmodel import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ..models import Subject, SubjectType

logger = logging.getLogger(__name__)


class SubjectRepo:
    """
    Subject 数据访问层
    封装所有与 Subject 相关的数据库操作
    """
    
    @staticmethod
    async def create(db: AsyncSession, subject_data: Dict[str, Any], source: str = "bangumi", source_id: Optional[str] = None) -> Subject:
        """
        创建新的 Subject 记录
        
        Args:
            db: 数据库会话
            subject_data: Subject数据，可以是嵌套的(收藏列表中的)或完整的(详情接口)，数据结构参考 models/subject.py
            source: 数据源 (bangumi/douban)，默认为 bangumi
            source_id: 原站ID，如果不提供则从 subject_data 中提取
        
        Returns:
            创建的Subject对象
        
        Raises:
            ValueError: 缺少必要的Subject ID
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 处理Type A (嵌套在收藏数据中的Subject)
            if "subject" in subject_data:
                subject_data = subject_data["subject"]
            
            # 如果没有提供 source_id，则从 subject_data 中提取
            if not source_id:
                subject_id = subject_data.get("id")
                if not subject_id:
                    raise ValueError("Subject ID is required")
                source_id = str(subject_id)
            
            # 处理Subject类型
            subject_type = subject_data.get("type")
            try:
                type_enum = SubjectType(subject_type) if subject_type else None
            except ValueError:
                logger.warning(f"未知的Subject类型: {subject_type}, 将使用None")
                type_enum = None
            
            # 构造 Subject 数据，显式设置 source 和 source_id
            subject_fields = {
                "source": source,
                "source_id": source_id,
                "type": type_enum,
                "name": subject_data.get("name", ""),
                "name_cn": subject_data.get("name_cn", ""),
                "summary": subject_data.get("summary"),
                "date": subject_data.get("date", ""),
                "platform": subject_data.get("platform", ""),
                "images": subject_data.get("images", {}),
                "image": subject_data.get("image", ""),
                "tags": subject_data.get("tags", []),
                "meta_tags": subject_data.get("meta_tags", []),
                "infobox": subject_data.get("infobox", []),
                "rating": subject_data.get("rating", {}),
                "collection": subject_data.get("collection", {}),
                "eps": subject_data.get("eps"),
                "volumes": subject_data.get("volumes"),
                "series": subject_data.get("series", False),
                "locked": subject_data.get("locked", False),
                "nsfw": subject_data.get("nsfw", False)
            }
            
            new_subject = Subject(**subject_fields)
            db.add(new_subject)
            await db.commit()
            await db.refresh(new_subject)
            return new_subject
        except SQLAlchemyError as e:
            logger.error(f"创建Subject失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_id(db: AsyncSession, subject_id: int) -> Optional[Subject]:
        """
        根据ID获取Subject
        
        Args:
            db: 数据库会话
            subject_id: Subject ID
        
        Returns:
            Subject对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(Subject).where(Subject.id == subject_id))
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取Subject失败: {e}")
            raise
    
    @staticmethod
    async def get_by_source(db: AsyncSession, source: str, source_id: str) -> Optional[Subject]:
        """
        根据数据源和ID查找Subject
        
        Args:
            db: 数据库会话
            source: 数据源
            source_id: 原站ID
        
        Returns:
            Subject对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(
                select(Subject).where(
                    Subject.source == source,
                    Subject.source_id == source_id
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取Subject失败: {e}")
            raise
    
    @staticmethod
    async def search_by_name(db: AsyncSession, name: str, skip: int = 0, limit: int = 20) -> List[Subject]:
        """
        根据名称搜索Subject（支持模糊匹配）
        
        Args:
            db: 数据库会话
            name: 搜索名称
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            Subject对象列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            search_term = f"%{name}%"
            result = await db.execute(
                select(Subject).where(
                    or_(
                        Subject.name.ilike(search_term),
                        Subject.name_cn.ilike(search_term)
                    )
                ).offset(skip).limit(limit)
            )
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"搜索Subject失败: {e}")
            raise
    
    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100, subject_type: Optional[int] = None) -> List[Subject]:
        """
        获取所有Subject记录
        
        Args:
            db: 数据库会话
            skip: 跳过的记录数
            limit: 返回的最大记录数
            subject_type: 可选，条目类型过滤
        
        Returns:
            Subject对象列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            query = select(Subject)
            
            if subject_type is not None:
                query = query.where(Subject.type == subject_type)
            
            result = await db.execute(query.offset(skip).limit(limit))
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"获取Subject列表失败: {e}")
            raise
    
    @staticmethod
    async def update(db: AsyncSession, subject_id: int, subject_data: Dict[str, Any]) -> Optional[Subject]:
        """
        更新Subject信息
        
        Args:
            db: 数据库会话
            subject_id: Subject ID
            subject_data: 更新的Subject数据，数据结构参考 models/subject.py
        
        Returns:
            更新后的Subject对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            subject = await SubjectRepo.get_by_id(db, subject_id)
            if not subject:
                return None
            
            # 处理Subject类型
            if "type" in subject_data:
                subject_type = subject_data["type"]
                try:
                    subject_type_enum = SubjectType(subject_type) if subject_type else None
                except ValueError:
                    logger.warning(f"未知的Subject类型: {subject_type}, 将忽略该字段")
                    subject_type_enum = None
                subject.type = subject_type_enum
            
            # 更新其他字段
            update_fields = [
                "name", "name_cn", "summary", "date", "platform", 
                "images", "image", "tags", "meta_tags", "infobox", 
                "rating", "collection", "eps", "volumes", 
                "series", "locked", "nsfw"
            ]
            
            for field in update_fields:
                if field in subject_data:
                    setattr(subject, field, subject_data[field])
            
            db.add(subject)
            await db.commit()
            await db.refresh(subject)
            return subject
        except SQLAlchemyError as e:
            logger.error(f"更新Subject失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def delete(db: AsyncSession, subject_id: int) -> bool:
        """
        删除Subject
        
        Args:
            db: 数据库会话
            subject_id: Subject ID
        
        Returns:
            删除成功返回True，Subject不存在返回False
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            subject = await SubjectRepo.get_by_id(db, subject_id)
            if not subject:
                return False
            
            await db.delete(subject)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除Subject失败: {e}")
            await db.rollback()
            raise
    
    
