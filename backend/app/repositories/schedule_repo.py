from typing import List, Optional
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError, IntegrityError
import traceback

from app.core.logging import get_logger
from ..models import Schedule, Subject, Collection
from ..schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleUpsert, ScheduleUpsertList

logger = get_logger(__name__)


class ScheduleRepository:
    """
    排班数据访问层
    封装所有与排班相关的数据库操作
    """
    
    @staticmethod
    async def get_by_user(db: AsyncSession, user_id: int) -> List[Schedule]:
        """
        获取指定用户的所有排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            用户的所有排班记录列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            query = select(Schedule).where(Schedule.user_id == user_id).order_by(Schedule.day_of_week, Schedule.start_time)
            result = await db.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"获取用户排班记录失败: {e}")
            raise
    
    @staticmethod
    async def get_unified_schedules_by_user(db: AsyncSession, user_id: int) -> List[tuple[Schedule, Optional[Subject], Optional[Collection]]]:
        """
        获取指定用户的所有排班记录，附带左外连接的条目和收藏信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            用户的所有排班记录列表，每个元素是 (Schedule, Subject, Collection) 的元组
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 构建查询，使用左外连接
            query = (
                select(Schedule, Subject, Collection)
                .where(Schedule.user_id == user_id)
                .outerjoin(Subject, (Schedule.source == Subject.source) & (Schedule.source_id == Subject.source_id))
                .outerjoin(Collection, (Schedule.source == Collection.source) & (Schedule.source_id == Collection.source_id) & (Collection.user_id == user_id))
                .order_by(Schedule.day_of_week, Schedule.start_time)
            )
            result = await db.execute(query)
            return result.all()
        except SQLAlchemyError as e:
            logger.error(f"获取用户统一排班记录失败: {e}")
            raise
    
    @staticmethod
    async def create_for_user(db: AsyncSession, user_id: int, schedule_data: ScheduleCreate | dict) -> Schedule:
        """
        为指定用户创建排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            schedule_data: 排班数据，使用 ScheduleCreate schema 或字典
        
        Returns:
            创建的排班记录
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 提取数据
            data = schedule_data.model_dump() if hasattr(schedule_data, 'model_dump') else schedule_data
            
            # 移除 data 中的 user_id，避免重复传递
            data.pop('user_id', None)
            
            # 检查是否存在相同的排班（同一用户、同一天、同一时间）
            existing_schedule = await ScheduleRepository._get_existing_schedule(
                db, user_id, data['day_of_week'], data['start_time']
            )
            if existing_schedule:
                logger.warning(f"用户 {user_id} 在 {data['day_of_week']} {data['start_time']} 已存在排班记录")
                return existing_schedule
            
            # 创建新的排班记录
            new_schedule = Schedule(
                user_id=user_id,
                **data
            )
            db.add(new_schedule)
            await db.commit()
            await db.refresh(new_schedule)
            return new_schedule
        except IntegrityError as e:
            logger.error(f"创建排班记录时数据完整性错误: {e}")
            await db.rollback()
            raise
        except SQLAlchemyError as e:
            logger.error(f"创建排班记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_id(db: AsyncSession, schedule_id: int) -> Optional[Schedule]:
        """
        根据ID获取排班记录
        
        Args:
            db: 数据库会话
            schedule_id: 排班ID
        
        Returns:
            排班记录或None
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            query = select(Schedule).where(Schedule.id == schedule_id)
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"获取排班记录失败: {e}")
            raise
    
    @staticmethod
    async def update(db: AsyncSession, schedule_id: int, user_id: int, schedule_data: ScheduleUpdate | dict) -> Optional[Schedule]:
        """
        更新排班记录（需校验user_id）
        
        Args:
            db: 数据库会话
            schedule_id: 排班ID
            user_id: 用户ID（用于校验）
            schedule_data: 更新的排班数据，使用 ScheduleUpdate schema 或字典
        
        Returns:
            更新后的排班记录或None（如果记录不存在或不属于该用户）
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 获取排班记录
            schedule = await ScheduleRepository.get_by_id(db, schedule_id)
            if not schedule:
                return None
            
            # 校验用户ID
            if schedule.user_id != user_id:
                return None
            
            # 提取更新数据
            update_data = schedule_data.model_dump(exclude_unset=True) if hasattr(schedule_data, 'model_dump') else schedule_data
            
            # 检查是否与其他排班冲突
            if 'day_of_week' in update_data or 'start_time' in update_data:
                new_day = update_data.get('day_of_week', schedule.day_of_week)
                new_time = update_data.get('start_time', schedule.start_time)
                existing_schedule = await ScheduleRepository._get_existing_schedule(
                    db, user_id, new_day, new_time, exclude_id=schedule_id
                )
                if existing_schedule:
                    logger.warning(f"用户 {user_id} 在 {new_day} {new_time} 已存在其他排班记录")
                    return None
            
            # 更新字段
            for field, value in update_data.items():
                setattr(schedule, field, value)
            
            await db.commit()
            await db.refresh(schedule)
            return schedule
        except IntegrityError as e:
            logger.error(f"更新排班记录时数据完整性错误: {e}")
            await db.rollback()
            raise
        except SQLAlchemyError as e:
            logger.error(f"更新排班记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def delete(db: AsyncSession, schedule_id: int, user_id: int) -> bool:
        """
        删除排班记录（需校验user_id）
        
        Args:
            db: 数据库会话
            schedule_id: 排班ID
            user_id: 用户ID（用于校验）
        
        Returns:
            是否删除成功
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            # 获取排班记录
            schedule = await ScheduleRepository.get_by_id(db, schedule_id)
            if not schedule:
                return False
            
            # 校验用户ID
            if schedule.user_id != user_id:
                return False
            
            # 删除记录
            await db.delete(schedule)
            await db.commit()
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除排班记录失败: {e}")
            await db.rollback()
            raise
    
    @staticmethod
    async def get_by_day(db: AsyncSession, user_id: int, day_of_week: int) -> List[Schedule]:
        """
        获取用户指定星期的排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            day_of_week: 星期几，0-6 (周日到周六)
        
        Returns:
            指定星期的排班记录列表
        
        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            query = select(Schedule).where(
                Schedule.user_id == user_id,
                Schedule.day_of_week == day_of_week
            ).order_by(Schedule.start_time)
            result = await db.execute(query)
            return result.scalars().all()
        except SQLAlchemyError as e:
            logger.error(f"获取指定星期的排班记录失败: {e}")
            raise
    
    @staticmethod
    async def _get_existing_schedule(
        db: AsyncSession, 
        user_id: int, 
        day_of_week: int, 
        start_time: str, 
        exclude_id: Optional[int] = None
    ) -> Optional[Schedule]:
        """
        检查是否存在相同的排班记录

        Args:
            db: 数据库会话
            user_id: 用户ID
            day_of_week: 星期几
            start_time: 开始时间
            exclude_id: 排除的排班ID（用于更新操作）

        Returns:
            存在的排班记录或None
        """
        try:
            query = select(Schedule).where(
                Schedule.user_id == user_id,
                Schedule.day_of_week == day_of_week,
                Schedule.start_time == start_time
            )
            if exclude_id:
                query = query.where(Schedule.id != exclude_id)
            result = await db.execute(query)
            return result.scalar_one_or_none()
        except SQLAlchemyError as e:
            logger.error(f"检查重复排班记录失败: {e}")
            return None
    
    @staticmethod
    async def delete_all_by_user(db: AsyncSession, user_id: int) -> bool:
        """
        删除指定用户的所有排班记录

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            是否删除成功

        Raises:
            SQLAlchemyError: 数据库操作异常
        """
        try:
            logger.info(f"开始删除用户 {user_id} 的所有排班记录")
            logger.debug(f"数据库会话: {db}")
            
            # 构建删除查询
            delete_query = Schedule.__table__.delete().where(Schedule.user_id == user_id)
            logger.debug(f"删除查询: {delete_query}")
            
            # 执行删除操作
            result = await db.execute(delete_query)
            logger.info(f"删除操作结果: {result}")
            logger.info(f"删除的记录数: {result.rowcount}")
            
            # 提交事务
            await db.commit()
            logger.info(f"事务提交成功")
            
            logger.info(f"成功删除用户 {user_id} 的所有排班记录，共删除 {result.rowcount} 条")
            return True
        except SQLAlchemyError as e:
            logger.error(f"删除用户 {user_id} 所有排班记录失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await db.rollback()
            logger.info(f"事务回滚成功")
            raise
    
    @staticmethod
    async def batch_upsert(db: AsyncSession, user_id: int, schedule_upsert_list: ScheduleUpsertList) -> int:
        """
        批量 Upsert 排班记录

        Args:
            db: 数据库会话
            user_id: 用户ID
            schedule_upsert_list: 排班记录列表，使用 ScheduleUpsertList schema

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
                logger.error("Deploy mode not supported")
                return 0

            if not schedule_upsert_list.items:
                return 0
            
            # 固定的唯一键字段 - 对于排班记录，使用用户ID、来源和来源ID作为唯一键
            unique_fields = ['user_id', 'source', 'source_id']
            
            # 1. 将 ScheduleUpsert 对象转换为字典列表，并进行数据清洗
            schedule_dicts = []
            logger.info(f"开始处理 {len(schedule_upsert_list.items)} 条排班记录")
            
            for i, schedule_upsert in enumerate(schedule_upsert_list.items):
                # 使用 model_dump 转换为字典，排除 unset 的字段
                schedule_dict = schedule_upsert.model_dump(exclude_unset=True)
                
                # 确保用户ID一致
                schedule_dict['user_id'] = user_id
                
                # 数据清洗：确保必要字段存在
                if 'day_of_week' not in schedule_dict:
                    schedule_dict['day_of_week'] = 0
                if 'start_time' not in schedule_dict:
                    schedule_dict['start_time'] = '00:00'
                if 'watch_type' not in schedule_dict:
                    schedule_dict['watch_type'] = 4  # 默认 NEW 类型
                if 'duration' not in schedule_dict:
                    schedule_dict['duration'] = 1
                
                schedule_dicts.append(schedule_dict)
            
            if not schedule_dicts:
                return 0

            # ================= 统一数据结构 =================
            # SQLAlchemy 批量插入要求所有字典的 key 必须一致
            # 获取所有字典中出现过的所有 key 的并集
            all_keys = set().union(*(d.keys() for d in schedule_dicts))
            
            # 回填缺失的 key 为 None
            for d in schedule_dicts:
                for k in all_keys:
                    if k not in d:
                        d[k] = None
            
            logger.info(f"数据清洗与结构统一完成，共处理 {len(schedule_dicts)} 条数据")
            # ===============================================
            
            # 3. 构建 Insert 语句
            stmt = insert(Schedule).values(schedule_dicts)
            
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
            result = await db.execute(stmt)
            await db.commit()
            
            logger.info(f"批量 Upsert 完成: {len(schedule_dicts)} 个排班记录处理成功")
            return len(schedule_dicts)
            
        except SQLAlchemyError as e:
            logger.error(f"批量 Upsert 排班记录失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await db.rollback()
            raise

    @staticmethod
    async def upsert(db: AsyncSession, user_id: int, schedule_upsert: ScheduleUpsert) -> Schedule:
        """
        Upsert 单个排班记录

        Args:
            db: 数据库会话
            user_id: 用户ID
            schedule_upsert: 排班记录数据，使用 ScheduleUpsert schema

        Returns:
            处理后的排班记录

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
                logger.error("Deploy mode not supported")
                return None

            # 固定的唯一键字段 - 对于排班记录，使用用户ID、来源和来源ID作为唯一键
            unique_fields = ['user_id', 'source', 'source_id']
            
            # 1. 将 ScheduleUpsert 对象转换为字典，并进行数据清洗
            schedule_dict = schedule_upsert.model_dump(exclude_unset=True) if hasattr(schedule_upsert, 'model_dump') else schedule_upsert
            
            # 确保用户ID一致
            schedule_dict['user_id'] = user_id
            
            # 数据清洗：确保必要字段存在
            if 'day_of_week' not in schedule_dict:
                schedule_dict['day_of_week'] = 0
            if 'start_time' not in schedule_dict:
                schedule_dict['start_time'] = '00:00'
            if 'watch_type' not in schedule_dict:
                schedule_dict['watch_type'] = 4  # 默认 NEW 类型
            if 'duration' not in schedule_dict:
                schedule_dict['duration'] = 1

            logger.info(f"开始处理单个排班记录: user_id={user_id}, source={schedule_dict.get('source')}, source_id={schedule_dict.get('source_id')}")

            # 2. 构建 Insert 语句
            stmt = insert(Schedule).values(schedule_dict)
            
            # 3. 自动计算需要更新的字段 (除了 unique_fields 以外的所有字段)
            # 仅更新本次数据中包含的字段，避免更新那些完全没有传的字段
            # 同时排除 created_at 和 id 等不应更新的字段
            non_updatable_fields = {'id', 'created_at'}
            update_cols = set(schedule_dict.keys()) - set(unique_fields) - non_updatable_fields
            
            # 4. 构建 set_ 字典
            set_dict = {col: getattr(stmt.excluded, col) for col in update_cols}
            
            # 5. 添加 On Conflict 子句
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
            
            # 6. 执行语句
            result = await db.execute(stmt)
            await db.commit()
            
            # 7. 获取处理后的记录
            # 构建查询语句，使用唯一键字段
            from sqlmodel import select
            query = select(Schedule).where(
                Schedule.user_id == user_id,
                Schedule.source == schedule_dict['source'],
                Schedule.source_id == schedule_dict['source_id']
            )
            result = await db.execute(query)
            updated_schedule = result.scalar_one_or_none()
            
            logger.info(f"Upsert 完成: 排班记录处理成功")
            return updated_schedule
            
        except SQLAlchemyError as e:
            logger.error(f"Upsert 排班记录失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            await db.rollback()
            raise
