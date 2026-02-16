from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Schedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate
from app.repositories.schedule_repo import ScheduleRepository

logger = get_logger(__name__)


class ScheduleService:
    """
    排班服务层
    处理与排班相关的业务逻辑
    """
    
    @staticmethod
    async def get_user_schedules(db: AsyncSession, user_id: int) -> List[Schedule]:
        """
        获取用户的所有排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            用户的所有排班记录列表
        """
        try:
            logger.info(f"获取用户 {user_id} 的所有排班记录")
            schedules = await ScheduleRepository.get_by_user(db, user_id)
            logger.info(f"成功获取用户 {user_id} 的排班记录，共 {len(schedules)} 条")
            return schedules
        except Exception as e:
            logger.error(f"获取用户排班记录失败: {e}")
            raise
    
    @staticmethod
    async def create_schedule(db: AsyncSession, user_id: int, schedule_data: ScheduleCreate) -> Optional[Schedule]:
        """
        为用户创建新的排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            schedule_data: 排班数据，使用 ScheduleCreate schema
        
        Returns:
            创建的排班记录或None（如果已存在相同的排班）
        
        Raises:
            Exception: 创建过程中的异常
        """
        try:
            logger.info(f"为用户 {user_id} 创建新的排班记录: {schedule_data}")
            # 这里可以添加额外的业务逻辑，例如：
            # 1. 校验 subject_id 是否存在于 Bangumi
            # 2. 检查是否与现有排班时间冲突
            # 3. 其他业务规则校验
            
            # 创建排班记录
            new_schedule = await ScheduleRepository.create_for_user(db, user_id, schedule_data)
            logger.info(f"成功为用户 {user_id} 创建排班记录: {new_schedule.id}")
            return new_schedule
        except Exception as e:
            logger.error(f"创建排班记录失败: {e}")
            raise
    
    @staticmethod
    async def update_schedule(db: AsyncSession, schedule_id: int, user_id: int, schedule_data: ScheduleUpdate) -> Optional[Schedule]:
        """
        更新用户的排班记录
        
        Args:
            db: 数据库会话
            schedule_id: 排班ID
            user_id: 用户ID
            schedule_data: 更新的排班数据，使用 ScheduleUpdate schema
        
        Returns:
            更新后的排班记录或None（如果记录不存在、不属于该用户或存在冲突）
        """
        try:
            logger.info(f"更新用户 {user_id} 的排班记录 {schedule_id}: {schedule_data}")
            # 更新排班记录
            updated_schedule = await ScheduleRepository.update(db, schedule_id, user_id, schedule_data)
            if updated_schedule:
                logger.info(f"成功更新用户 {user_id} 的排班记录: {schedule_id}")
            else:
                logger.warning(f"更新排班记录失败: 记录不存在或不属于用户 {user_id}")
            return updated_schedule
        except Exception as e:
            logger.error(f"更新排班记录失败: {e}")
            raise
    
    @staticmethod
    async def delete_schedule(db: AsyncSession, schedule_id: int, user_id: int) -> bool:
        """
        删除用户的排班记录
        
        Args:
            db: 数据库会话
            schedule_id: 排班ID
            user_id: 用户ID
        
        Returns:
            是否删除成功
        """
        try:
            logger.info(f"删除用户 {user_id} 的排班记录 {schedule_id}")
            # 删除排班记录
            deleted = await ScheduleRepository.delete(db, schedule_id, user_id)
            if deleted:
                logger.info(f"成功删除用户 {user_id} 的排班记录: {schedule_id}")
            else:
                logger.warning(f"删除排班记录失败: 记录不存在或不属于用户 {user_id}")
            return deleted
        except Exception as e:
            logger.error(f"删除排班记录失败: {e}")
            raise
    
    @staticmethod
    async def get_schedules_by_day(db: AsyncSession, user_id: int, day_of_week: int) -> List[Schedule]:
        """
        获取用户指定星期的排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            day_of_week: 星期几，0-6 (周日到周六)
        
        Returns:
            指定星期的排班记录列表
        """
        try:
            logger.info(f"获取用户 {user_id} 在星期 {day_of_week} 的排班记录")
            # 使用新的 repository 方法直接获取指定星期的排班记录
            schedules = await ScheduleRepository.get_by_day(db, user_id, day_of_week)
            logger.info(f"成功获取用户 {user_id} 在星期 {day_of_week} 的排班记录，共 {len(schedules)} 条")
            return schedules
        except Exception as e:
            logger.error(f"获取指定星期的排班记录失败: {e}")
            raise
