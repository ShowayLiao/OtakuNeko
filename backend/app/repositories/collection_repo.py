from typing import Dict, Any, Optional, List
import logging
from datetime import datetime
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ..models import Collection, CollectionStatus

logger = logging.getLogger(__name__)


class CollectionRepo:
    """
    Collection 数据访问层
    封装所有与 Collection 相关的数据库操作
    """
    
    @staticmethod
    async def create(db: AsyncSession, user_id: int, subject_id: int, collection_data: Dict[str, Any]) -> Collection:
        """
        创建新的 Collection 记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_id: 条目ID
            collection_data: 收藏数据
        
        Returns:
            创建的Collection对象
        
        Raises:
            ValueError: 缺少必要的更新时间
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 提取收藏状态
            collection_type = collection_data.get("type")
            try:
                collection_status = CollectionStatus(collection_type) if collection_type else None
            except ValueError:
                logger.warning(f"未知的收藏状态: {collection_type}，将使用None")
                collection_status = None
            
            # 提取其他收藏元数据
            rate = collection_data.get("rate")
            comment = collection_data.get("comment") or collection_data.get("remark") or ""
            updated_at_str = collection_data.get("updated_at")
            
            # 提取标签
            tags = collection_data.get("tags", [])
            if tags and isinstance(tags, list):
                # 如果是字符串列表，直接使用
                if all(isinstance(tag, str) for tag in tags):
                    tags_list = tags
                # 如果是对象列表，提取 name 字段
                elif all(isinstance(tag, dict) and "name" in tag for tag in tags):
                    tags_list = [tag["name"] for tag in tags]
                else:
                    tags_list = []
            else:
                tags_list = []
            
            if not updated_at_str:
                raise ValueError("Updated at time is required")
            
            # 转换更新时间字符串为 datetime 对象
            updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
            
            # 关键修改：如果有时区信息，将其移除 (Make it naive)
            if updated_at.tzinfo is not None:
                updated_at = updated_at.replace(tzinfo=None)
            
            private = collection_data.get("private", False)
            
            # 构造Collection数据
            collection_fields = {
                "user_id": user_id,
                "subject_id": subject_id,
                "type": collection_status,
                "rate": rate,
                "comment": comment,
                "updated_at": updated_at,
                "private": private,
                "tags": tags_list
            }
            
            new_collection = Collection(**collection_fields)
            db.add(new_collection)
            await db.commit()
            await db.refresh(new_collection)
            return new_collection
        except SQLAlchemyError as e:
            logger.error(f"创建收藏记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_user_and_subject(db: AsyncSession, user_id: int, subject_id: int) -> Optional[Collection]:
        """
        根据用户ID和条目ID获取Collection
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_id: 条目ID
        
        Returns:
            Collection对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(
                select(Collection).where(
                    Collection.user_id == user_id,
                    Collection.subject_id == subject_id
                )
            )
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取收藏记录失败: {e}")
            raise
    
    @staticmethod
    async def get_by_user(db: AsyncSession, user_id: int, subject_type: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Collection]:
        """
        根据用户ID获取所有Collection
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_type: 可选，条目类型过滤
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            Collection对象列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            from ..models import Subject
            
            query = select(Collection).where(Collection.user_id == user_id)
            
            if subject_type is not None:
                query = query.join(Subject).where(Subject.type == subject_type)
            
            result = await db.execute(query.offset(skip).limit(limit))
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"获取用户收藏列表失败: {e}")
            raise
    
    @staticmethod
    async def get_all(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[Collection]:
        """
        获取所有Collection记录
        
        Args:
            db: 数据库会话
            skip: 跳过的记录数
            limit: 返回的最大记录数
        
        Returns:
            Collection对象列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            result = await db.execute(select(Collection).offset(skip).limit(limit))
            return list(result.scalars().all())
        except SQLAlchemyError as e:
            logger.error(f"获取收藏列表失败: {e}")
            raise
    
    @staticmethod
    async def update(db: AsyncSession, user_id: int, subject_id: int, collection_data: Dict[str, Any]) -> Optional[Collection]:
        """
        更新 Collection 记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_id: 条目ID
            collection_data: 更新的收藏数据
        
        Returns:
            更新后的Collection对象或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject_id)
            if not collection:
                return None
            
            # 提取收藏状态
            if "type" in collection_data:
                collection_type = collection_data["type"]
                try:
                    collection_status = CollectionStatus(collection_type) if collection_type else None
                except ValueError:
                    logger.warning(f"未知的收藏状态: {collection_type}，将使用None")
                    collection_status = None
                collection.type = collection_status
            
            # 提取其他收藏元数据
            if "rate" in collection_data:
                collection.rate = collection_data["rate"]
            
            if "comment" in collection_data:
                collection.comment = collection_data["comment"]
            elif "remark" in collection_data:
                collection.comment = collection_data["remark"]
            
            if "updated_at" in collection_data:
                updated_at_str = collection_data["updated_at"]
                # 转换更新时间字符串为 datetime 对象
                updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                # 关键修改：如果有时区信息，将其移除 (Make it naive)
                if updated_at.tzinfo is not None:
                    updated_at = updated_at.replace(tzinfo=None)
                collection.updated_at = updated_at
            
            if "tags" in collection_data:
                tags = collection_data["tags"]
                if tags and isinstance(tags, list):
                    # 如果是字符串列表，直接使用
                    if all(isinstance(tag, str) for tag in tags):
                        tags_list = tags
                    # 如果是对象列表，提取 name 字段
                    elif all(isinstance(tag, dict) and "name" in tag for tag in tags):
                        tags_list = [tag["name"] for tag in tags]
                    else:
                        tags_list = []
                else:
                    tags_list = []
                collection.tags = tags_list
            
            if "private" in collection_data:
                collection.private = collection_data["private"]
            
            db.add(collection)
            await db.commit()
            await db.refresh(collection)
            return collection
        except SQLAlchemyError as e:
            logger.error(f"更新收藏记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def delete(db: AsyncSession, user_id: int, subject_id: int) -> bool:
        """
        删除 Collection 记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_id: 条目ID
        
        Returns:
            删除成功返回True，收藏记录不存在返回False
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject_id)
            if not collection:
                return False
            
            await db.delete(collection)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除收藏记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def save(db: AsyncSession, user_id: int, subject_id: int, collection_data: Dict[str, Any]) -> Collection:
        """
        保存或更新 Collection 记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            subject_id: 条目ID
            collection_data: 收藏数据
        
        Returns:
            更新或创建的Collection对象
        
        Raises:
            ValueError: 缺少必要的更新时间
            SQLAlchemyError: 数据库操作异常
        """
        # 提取收藏状态
        collection_type = collection_data.get("type")
        try:
            collection_status = CollectionStatus(collection_type) if collection_type else None
        except ValueError:
            logger.warning(f"未知的收藏状态: {collection_type}，将使用None")
            collection_status = None
        
        # 提取其他收藏元数据
        rate = collection_data.get("rate")
        comment = collection_data.get("comment") or collection_data.get("remark") or ""
        updated_at_str = collection_data.get("updated_at")
        
        # 提取标签
        tags = collection_data.get("tags", [])
        if tags and isinstance(tags, list):
            # 如果是字符串列表，直接使用
            if all(isinstance(tag, str) for tag in tags):
                tags_list = tags
            # 如果是对象列表，提取 name 字段
            elif all(isinstance(tag, dict) and "name" in tag for tag in tags):
                tags_list = [tag["name"] for tag in tags]
            else:
                tags_list = []
        else:
            tags_list = []
        
        if not updated_at_str:
            raise ValueError("Updated at time is required")
        
        # 转换更新时间字符串为 datetime 对象
        updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
        
        # 关键修改：如果有时区信息，将其移除 (Make it naive)
        if updated_at.tzinfo is not None:
            updated_at = updated_at.replace(tzinfo=None)
        
        private = collection_data.get("private", False)
        
        # 查询是否已存在收藏记录
        existing_collection = await CollectionRepo.get_by_user_and_subject(db, user_id, subject_id)
        
        # 构造Collection数据
        collection_fields = {
            "user_id": user_id,
            "subject_id": subject_id,
            "type": collection_status,
            "rate": rate,
            "comment": comment,
            "updated_at": updated_at,
            "private": private,
            "tags": tags_list
        }
        
        if existing_collection:
            # 更新现有记录
            for field, value in collection_fields.items():
                setattr(existing_collection, field, value)
            db.add(existing_collection)
            await db.commit()
            await db.refresh(existing_collection)
            return existing_collection
        else:
            # 创建新记录
            return await CollectionRepo.create(db, user_id, subject_id, collection_data)
