from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
import traceback

from app.core.logging import get_logger
from app.models import Schedule
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleUpsert,
    ScheduleUpsertList,
    ScheduleRead,
    UnifiedSchedule,
    UnifiedScheduleList,
)
from app.repositories.schedule_repo import ScheduleRepository

# 导入 Bangumi 相关服务
from .bangumi_service import get_bangumi_calendar
from .bangumi_data_sync import BangumiDataSyncService

# 导入 Subject 相关服务
from .subject_service import batch_upsert_subjects

# 导入适配器
from app.schemas.adaptersV2 import (
    bangumi_calendar_to_subject_upsert_list,
    UnifiedList,
    UnifiedCollectionSubject,
)
from app.schemas.subject import SubjectRead, SubjectUpsertList
from app.schemas.collection import CollectionRead

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
            logger.error(
                "schedule_read_failed",
                extra={"action": "list_schedules", "error_type": type(e).__name__},
            )
            raise

    @staticmethod
    async def get_unified_user_schedules(
        db: AsyncSession, user_id: int
    ) -> UnifiedScheduleList:
        """
        获取用户的所有排班记录，附带关联的条目和收藏信息

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            包含排班记录及其关联信息的统一列表
        """
        try:
            logger.info(f"获取用户 {user_id} 的统一排班记录")
            # 调用 repository 方法获取带有关联数据的排班记录
            unified_schedules = await ScheduleRepository.get_unified_schedules_by_user(
                db, user_id
            )
            logger.info(
                f"成功获取用户 {user_id} 的统一排班记录，共 {len(unified_schedules)} 条"
            )

            # 转换为 UnifiedSchedule 格式
            items = []
            for schedule, subject, collection in unified_schedules:
                # 创建 UnifiedSchedule 对象
                unified_item = UnifiedSchedule(
                    schedule=ScheduleRead.model_validate(
                        schedule, from_attributes=True
                    ),
                    subject=(
                        SubjectRead.model_validate(subject, from_attributes=True)
                        if subject is not None
                        else None
                    ),
                    collection=(
                        CollectionRead.model_validate(collection, from_attributes=True)
                        if collection is not None
                        else None
                    ),
                )
                items.append(unified_item)

            # 创建并返回 UnifiedScheduleList
            return UnifiedScheduleList(items=items, total=len(items))
        except Exception as e:
            logger.error(
                "schedule_read_failed",
                extra={
                    "action": "list_unified_schedules",
                    "error_type": type(e).__name__,
                },
            )
            raise

    @staticmethod
    async def create_schedule(
        db: AsyncSession, user_id: int, schedule_data: ScheduleCreate
    ) -> Optional[Schedule]:
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
            logger.info("schedule_create_started", extra={"action": "create_schedule"})
            # 这里可以添加额外的业务逻辑，例如：
            # 1. 校验 subject_id 是否存在于 Bangumi
            # 2. 检查是否与现有排班时间冲突
            # 3. 其他业务规则校验

            # 创建排班记录
            new_schedule = await ScheduleRepository.create_for_user(
                db, user_id, schedule_data
            )
            logger.info(
                "schedule_create_succeeded", extra={"action": "create_schedule"}
            )
            return new_schedule
        except Exception as e:
            logger.error(
                "schedule_write_failed",
                extra={"action": "create_schedule", "error_type": type(e).__name__},
            )
            raise

    @staticmethod
    async def update_schedule(
        db: AsyncSession, schedule_id: int, user_id: int, schedule_data: ScheduleUpdate
    ) -> Optional[Schedule]:
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
            logger.info("schedule_update_started", extra={"action": "update_schedule"})
            # 更新排班记录
            updated_schedule = await ScheduleRepository.update(
                db, schedule_id, user_id, schedule_data
            )
            if updated_schedule:
                logger.info(
                    "schedule_update_succeeded", extra={"action": "update_schedule"}
                )
            else:
                logger.warning(
                    "schedule_update_not_applied",
                    extra={"action": "update_schedule"},
                )
            return updated_schedule
        except Exception as e:
            logger.error(
                "schedule_write_failed",
                extra={"action": "update_schedule", "error_type": type(e).__name__},
            )
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
            logger.info("schedule_delete_started", extra={"action": "delete_schedule"})
            # 删除排班记录
            deleted = await ScheduleRepository.delete(db, schedule_id, user_id)
            if deleted:
                logger.info(
                    "schedule_delete_succeeded", extra={"action": "delete_schedule"}
                )
            else:
                logger.warning(
                    "schedule_delete_not_applied",
                    extra={"action": "delete_schedule"},
                )
            return deleted
        except Exception as e:
            logger.error(
                "schedule_write_failed",
                extra={"action": "delete_schedule", "error_type": type(e).__name__},
            )
            raise

    @staticmethod
    async def get_schedules_by_day(
        db: AsyncSession, user_id: int, day_of_week: int
    ) -> List[Schedule]:
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
            logger.info(
                f"成功获取用户 {user_id} 在星期 {day_of_week} 的排班记录，共 {len(schedules)} 条"
            )
            return schedules
        except Exception as e:
            logger.error(
                "schedule_read_failed",
                extra={
                    "action": "list_schedules_by_day",
                    "error_type": type(e).__name__,
                },
            )
            raise

    @staticmethod
    async def upsert_schedule(
        db: AsyncSession, user_id: int, schedule_data: ScheduleUpsert
    ) -> Optional[Schedule]:
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
            logger.info("schedule_upsert_started", extra={"action": "upsert_schedule"})

            # 校验用户ID
            if schedule_data.user_id != user_id:
                logger.warning(
                    "schedule_upsert_rejected", extra={"action": "upsert_schedule"}
                )
                return None

            # 直接调用 repository 的 upsert 方法
            result = await ScheduleRepository.upsert(db, user_id, schedule_data)
            if result:
                logger.info(
                    "schedule_upsert_succeeded", extra={"action": "upsert_schedule"}
                )
            else:
                logger.warning(
                    "schedule_upsert_not_applied", extra={"action": "upsert_schedule"}
                )
            return result
        except Exception as e:
            logger.error(
                "schedule_write_failed",
                extra={"action": "upsert_schedule", "error_type": type(e).__name__},
            )
            raise

    @staticmethod
    async def bulk_upsert_schedules(
        db: AsyncSession, user_id: int, upsert_list: ScheduleUpsertList
    ) -> List[Schedule]:
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
            logger.info(
                "schedule_bulk_upsert_started",
                extra={"action": "bulk_upsert_schedules"},
            )

            # 直接调用 repository 的 batch_upsert 方法
            await ScheduleRepository.batch_upsert(db, user_id, upsert_list)
            logger.info(
                "schedule_bulk_upsert_succeeded",
                extra={"action": "bulk_upsert_schedules"},
            )

            # 由于 batch_upsert 返回的是处理的条目数量，而不是处理后的记录列表
            # 我们需要重新获取用户的所有排班记录
            updated_schedules = await ScheduleRepository.get_by_user(db, user_id)
            logger.info(
                "schedule_bulk_upsert_results_loaded",
                extra={"action": "bulk_upsert_schedules"},
            )

            return updated_schedules
        except Exception as e:
            logger.error(
                "schedule_write_failed",
                extra={
                    "action": "bulk_upsert_schedules",
                    "error_type": type(e).__name__,
                },
            )
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
            logger.info(
                "schedule_calendar_sync_started",
                extra={"action": "sync_bangumi_schedule"},
            )

            # 1. 调用 get_bangumi_calendar 获取日历数据
            logger.info(
                "schedule_calendar_fetch_started",
                extra={"action": "sync_bangumi_schedule"},
            )
            bangumi_calendar = await get_bangumi_calendar()
            logger.info(
                "schedule_calendar_fetch_succeeded",
                extra={"action": "sync_bangumi_schedule"},
            )

            # 2. 转换为 SubjectUpsertList
            logger.info(
                "schedule_calendar_conversion_started",
                extra={"action": "sync_bangumi_schedule"},
            )
            subject_upsert_list = bangumi_calendar_to_subject_upsert_list(
                bangumi_calendar
            )
            logger.info(
                "schedule_calendar_conversion_succeeded",
                extra={"action": "sync_bangumi_schedule"},
            )

            # 3. 批量填充 Airtime
            logger.info(
                "schedule_calendar_air_time_lookup_started",
                extra={"action": "sync_bangumi_schedule"},
            )
            # 提取所有的 source_id
            bangumi_ids = []
            for subject_upsert in subject_upsert_list.items:
                try:
                    bangumi_ids.append(int(subject_upsert.source_id))
                except ValueError:
                    logger.warning(
                        "schedule_calendar_source_id_invalid",
                        extra={"action": "sync_bangumi_schedule"},
                    )
                    continue

            # 调用 get_air_time_batch 获取时间字典
            air_time_dict = await BangumiDataSyncService.get_air_time_batch(
                db, bangumi_ids
            )
            logger.info(
                "schedule_calendar_air_time_lookup_succeeded",
                extra={"action": "sync_bangumi_schedule"},
            )

            # 记录第一个返回的时间值
            if air_time_dict:
                logger.info(
                    "schedule_calendar_air_time_sample_available",
                    extra={"action": "sync_bangumi_schedule"},
                )

            # 遍历 subject_upsert_list.items，填充 air_time
            for subject_upsert in subject_upsert_list.items:
                try:
                    bangumi_id = int(subject_upsert.source_id)
                    if bangumi_id in air_time_dict:
                        # 直接使用 ISO 格式的时间字符串
                        time_str = air_time_dict[bangumi_id]
                        # 将 ISO 格式的字符串转换为 datetime 对象
                        from datetime import datetime

                        subject_upsert.air_time = datetime.fromisoformat(time_str)
                        logger.debug(
                            "schedule_calendar_air_time_applied",
                            extra={"action": "sync_bangumi_schedule"},
                        )
                except ValueError:
                    logger.warning(
                        "schedule_calendar_source_id_invalid",
                        extra={"action": "sync_bangumi_schedule"},
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        "schedule_calendar_air_time_apply_failed",
                        extra={
                            "action": "sync_bangumi_schedule",
                            "error_type": type(e).__name__,
                        },
                    )
                    continue

                # 记录 air_weekday 值
                # logger.info(f"番剧 {subject_upsert.source_id} 的 air_weekday 值: {subject_upsert.air_weekday}")

            # 4. 批量插入数据（此时数据已包含时间）
            # bangumi-data 偶尔会给出缺少名称或类型的条目。写路径不再兜底成
            # ""/SubjectType.ANIME —— 空名称正是 scripts/cleanup_empty_subjects.py
            # 要清理的脏数据，所以这类条目直接跳过并记录，不让整批同步失败。
            valid_items = [
                item
                for item in subject_upsert_list.items
                if item.name and item.name.strip() and item.type is not None
            ]
            skipped = len(subject_upsert_list.items) - len(valid_items)
            if skipped:
                logger.error(
                    "schedule_calendar_invalid_items_skipped",
                    extra={"action": "sync_bangumi_schedule"},
                )
            if not valid_items:
                raise ValueError("Bangumi 日历没有可写入的有效条目（缺少名称或类型）")
            subject_upsert_list = SubjectUpsertList(
                total=len(valid_items), items=valid_items
            )

            logger.info(
                "schedule_calendar_subject_upsert_started",
                extra={"action": "sync_bangumi_schedule"},
            )
            logger.info(
                "schedule_calendar_subject_upsert_sample_available",
                extra={"action": "sync_bangumi_schedule"},
            )
            await batch_upsert_subjects(db, subject_upsert_list, user_id)
            logger.info(
                "schedule_calendar_subject_upsert_succeeded",
                extra={"action": "sync_bangumi_schedule"},
            )

            # 5. 批量转化为 unified 字段返回
            logger.info(
                "schedule_calendar_result_conversion_started",
                extra={"action": "sync_bangumi_schedule"},
            )
            unified_items = []

            # 构造 SubjectRead 对象
            first_item_processed = False
            for subject_upsert in subject_upsert_list.items:
                # 已在上面过滤过，这里同时完成类型收窄
                if not subject_upsert.name or subject_upsert.type is None:
                    continue

                # 记录第一个item的airtime值
                if not first_item_processed:
                    logger.info(
                        "schedule_calendar_result_sample_available",
                        extra={"action": "sync_bangumi_schedule"},
                    )
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
                    collection=None,  # 这里暂时不包含收藏数据
                )
                unified_items.append(unified_item)

            # 构造并返回 UnifiedList
            unified_list = UnifiedList(total=len(unified_items), items=unified_items)

            logger.info(
                "schedule_calendar_sync_succeeded",
                extra={"action": "sync_bangumi_schedule"},
            )
            return unified_list
        except Exception as e:
            logger.error(
                "schedule_write_failed",
                extra={
                    "action": "sync_bangumi_schedule",
                    "error_type": type(e).__name__,
                },
            )
            raise

    @staticmethod
    async def delete_all_schedules(db: AsyncSession, user_id: int) -> bool:
        """
        删除当前用户的所有排班记录

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            是否删除成功

        Raises:
            Exception: 删除过程中的异常
        """
        try:
            logger.info(f"开始删除用户 {user_id} 的所有排班记录")
            logger.debug(f"数据库会话: {db}")

            result = await ScheduleRepository.delete_all_by_user(db, user_id)
            logger.info(f"删除用户 {user_id} 所有排班记录的结果: {result}")
            logger.info(f"成功删除用户 {user_id} 的所有排班记录")
            return result
        except Exception as e:
            logger.error(f"删除用户 {user_id} 所有排班记录失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误堆栈: {traceback.format_exc()}")
            raise
