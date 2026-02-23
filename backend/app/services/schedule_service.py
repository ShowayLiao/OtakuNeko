from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Schedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleUpsert, ScheduleUpsertList, ScheduleReadList
from app.repositories.schedule_repo import ScheduleRepository

# 导入 Bangumi 相关服务
from .bangumi_service import get_bangumi_calendar
from .bangumi_data_sync import BangumiDataSyncService
# 导入 Subject 相关服务
from .subject_service import batch_upsert_subjects
# 导入适配器
from app.schemas.adaptersV2 import bangumi_calendar_to_subject_upsert_list, UnifiedList, UnifiedCollectionSubject
from app.schemas.subject import SubjectRead

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
    
    @staticmethod
    async def upsert_schedule(db: AsyncSession, user_id: int, schedule_data: ScheduleUpsert) -> Optional[Schedule]:
        """
        Upsert 排班记录（更新或插入）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            schedule_data: 排班数据，使用 ScheduleUpsert schema
        
        Returns:
            处理后的排班记录
        
        Raises:
            Exception: 处理过程中的异常
        """
        try:
            logger.info(f"Upsert 用户 {user_id} 的排班记录: {schedule_data}")
            
            # 校验用户ID
            if schedule_data.user_id != user_id:
                logger.warning(f"Upsert 排班记录失败: 用户ID不匹配")
                return None
            
            # 根据是否提供id决定执行更新还是插入
            if schedule_data.id:
                # 执行更新操作
                update_data = schedule_data.model_dump(exclude_unset=True, exclude={"id", "user_id"})
                updated_schedule = await ScheduleRepository.update(db, schedule_data.id, user_id, update_data)
                if updated_schedule:
                    logger.info(f"成功更新用户 {user_id} 的排班记录: {schedule_data.id}")
                else:
                    logger.warning(f"更新排班记录失败: 记录不存在或不属于用户 {user_id}")
                return updated_schedule
            else:
                # 执行插入操作
                create_data = schedule_data.model_dump(exclude={"id"})
                new_schedule = await ScheduleRepository.create_for_user(db, user_id, create_data)
                logger.info(f"成功为用户 {user_id} 创建排班记录: {new_schedule.id}")
                return new_schedule
        except Exception as e:
            logger.error(f"Upsert 排班记录失败: {e}")
            raise
    
    @staticmethod
    async def bulk_upsert_schedules(db: AsyncSession, user_id: int, upsert_list: ScheduleUpsertList) -> List[Schedule]:
        """
        批量 Upsert 排班记录
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            upsert_list: 待处理的排班记录列表
        
        Returns:
            处理后的排班记录列表
        
        Raises:
            Exception: 处理过程中的异常
        """
        try:
            logger.info(f"批量 Upsert 用户 {user_id} 的排班记录，共 {len(upsert_list.items)} 条")
            
            results = []
            for schedule_data in upsert_list.items:
                result = await ScheduleService.upsert_schedule(db, user_id, schedule_data)
                if result:
                    results.append(result)
            
            logger.info(f"批量 Upsert 完成，成功处理 {len(results)} 条记录")
            return results
        except Exception as e:
            logger.error(f"批量 Upsert 排班记录失败: {e}")
            raise
    
    @staticmethod
    async def sync_bangumi_calendar(db: AsyncSession, user_id: int) -> UnifiedList:
        """
        同步 Bangumi 日历数据
        
        步骤：
        1. 调用 get_bangumi_calendar 获取日历数据
        2. 转换为 SubjectUpsertList
        3. 批量插入数据
        4. 批量同步 airtime
        5. 批量转化为 unified 字段返回
        
        Args:
            db: 数据库会话
            user_id: 用户ID
        
        Returns:
            转换后的 UnifiedList 对象
        
        Raises:
            Exception: 同步过程中的异常
        """
        try:
            logger.info(f"开始同步 Bangumi 日历数据，用户ID: {user_id}")
            
            # 1. 调用 get_bangumi_calendar 获取日历数据
            logger.info("获取 Bangumi 日历数据")
            bangumi_calendar = await get_bangumi_calendar()
            logger.info("成功获取 Bangumi 日历数据")
            
            # 2. 转换为 SubjectUpsertList
            logger.info("转换数据格式为 SubjectUpsertList")
            subject_upsert_list = bangumi_calendar_to_subject_upsert_list(bangumi_calendar)
            logger.info(f"成功转换 {len(subject_upsert_list.items)} 条数据")
            
            # 3. 批量填充 Airtime
            logger.info("批量填充番剧放送时间")
            # 提取所有的 source_id
            bangumi_ids = []
            for subject_upsert in subject_upsert_list.items:
                try:
                    bangumi_ids.append(int(subject_upsert.source_id))
                except ValueError:
                    logger.warning(f"无效的 source_id: {subject_upsert.source_id}")
                    continue
            
            # 调用 get_air_time_batch 获取时间字典
            air_time_dict = await BangumiDataSyncService.get_air_time_batch(db, bangumi_ids)
            logger.info(f"成功获取 {len(air_time_dict)} 条番剧放送时间")
            
            # 记录第一个返回的时间值
            if air_time_dict:
                first_id = next(iter(air_time_dict))
                logger.info(f"第一个返回的时间值 - bangumi_id: {first_id}, time: {air_time_dict[first_id]}")
            
            # 遍历 subject_upsert_list.items，填充 air_time
            from datetime import time
            for subject_upsert in subject_upsert_list.items:
                try:
                    bangumi_id = int(subject_upsert.source_id)
                    if bangumi_id in air_time_dict:
                        # 直接使用 ISO 格式的时间字符串
                        time_str = air_time_dict[bangumi_id]
                        # 将 ISO 格式的字符串转换为 datetime 对象
                        from datetime import datetime
                        subject_upsert.air_time = datetime.fromisoformat(time_str)
                        logger.debug(f"填充番剧放送时间: {bangumi_id} -> {time_str}")
                except ValueError:
                    logger.warning(f"无效的 source_id: {subject_upsert.source_id}")
                    continue
                except Exception as e:
                    logger.warning(f"填充番剧放送时间失败: {e}")
                    continue
                
                # 记录 air_weekday 值
                # logger.info(f"番剧 {subject_upsert.source_id} 的 air_weekday 值: {subject_upsert.air_weekday}")
            
            # 4. 批量插入数据（此时数据已包含时间）
            logger.info("批量插入 Subject 数据")
            logger.info(f"第一条数据的 air_time 类型: {type(subject_upsert_list.items[0].air_time)}")
            logger.info(f"第一条数据的 air_time 值: {subject_upsert_list.items[0].air_time}")
            logger.info(f"第一条数据的 air_weekday 值: {subject_upsert_list.items[0].air_weekday}")
            processed_count = await batch_upsert_subjects(db, subject_upsert_list, user_id)
            logger.info(f"成功插入 {processed_count} 条数据")
            
            # 5. 批量转化为 unified 字段返回
            logger.info("转换为统一格式返回")
            unified_items = []
            
            # 构造 SubjectRead 对象
            first_item_processed = False
            for subject_upsert in subject_upsert_list.items:
                # 记录第一个item的airtime值
                if not first_item_processed:
                    logger.info(f"第一条数据的 air_time 值: {subject_upsert.air_time}")
                    logger.info(f"第一条数据的 air_weekday 值: {subject_upsert.air_weekday}")
                    first_item_processed = True
                
                subject_read = SubjectRead(
                    id=0,  # 默认ID，数据库中会生成
                    source=subject_upsert.source,
                    source_id=subject_upsert.source_id,
                    name=subject_upsert.name,
                    name_cn=subject_upsert.name_cn,
                    type=subject_upsert.type,
                    summary=subject_upsert.summary,
                    date=subject_upsert.date,
                    platform=subject_upsert.platform,
                    eps=subject_upsert.eps,
                    volumes=subject_upsert.volumes,
                    images=subject_upsert.images,
                    image=subject_upsert.image,
                    tags=subject_upsert.tags,
                    meta_tags=subject_upsert.meta_tags,
                    infobox=subject_upsert.infobox,
                    rating=subject_upsert.rating,
                    collection=subject_upsert.collection,
                    series=subject_upsert.series,
                    locked=subject_upsert.locked,
                    nsfw=subject_upsert.nsfw,
                    air_time=subject_upsert.air_time,
                    air_weekday=subject_upsert.air_weekday,
                )
                
                # 构造 UnifiedCollectionSubject 对象
                unified_item = UnifiedCollectionSubject(
                    subject=subject_read,
                    collection=None  # 这里暂时不包含收藏数据
                )
                unified_items.append(unified_item)
            
            # 构造并返回 UnifiedList
            unified_list = UnifiedList(
                total=len(unified_items),
                items=unified_items
            )
            
            logger.info(f"同步 Bangumi 日历数据完成，共处理 {len(unified_items)} 条记录")
            return unified_list
        except Exception as e:
            logger.error(f"同步 Bangumi 日历数据失败: {e}")
            raise
