import threading
import psutil
import os
import time
import uuid
import streamlit as st

class GlobalSessionManager:
    """
    全局会话管理器，用于控制并发访问人数
    使用字典结构存储会话信息：{session_id: {"status": "active"/"queued", "last_ping": timestamp}}
    实现自动剔除僵尸会话逻辑，仅清理排队中且超时的会话
    """
    _lock = threading.Lock()
    
    def __init__(self, max_total_sessions=20):
        # 配置参数
        self.MAX_TOTAL_SESSIONS = max_total_sessions
        # 使用字典存储会话信息：{session_id: {"status": "active"/"waiting", "last_ping": timestamp, "is_busy": bool, "entry_time": timestamp}}
        self._sessions = {}
        self._session_lock = threading.Lock()
        # 僵尸会话超时时间（秒）
        self._ZOMBIE_TIMEOUT = 30
        # 会话状态常量
        self.STATUS_ACTIVE = "active"  # 已进入系统的活跃用户
        self.STATUS_WAITING = "waiting"  # 正在排队的用户
        self.STATUS_NEW = "New"  # 完全新的会话ID
        self.STATUS_EXPIRED = "Expired"  # 明确被清理的会话ID
        # 存储明确被踢出的会话ID，缓存1分钟
        self._expired_ids = set()
        self._expired_ids_lock = threading.Lock()
        # 过期ID的缓存时间（秒）
        self._EXPIRED_IDS_TTL = 60
        # 启动后台监控线程
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
    
    def _get_available_memory_percent(self) -> float:
        """
        获取系统可用内存百分比
        兼容不同版本的psutil
        """
        mem = psutil.virtual_memory()
        # 计算可用内存百分比
        return (mem.available / mem.total) * 100
    
    def _is_system_congested(self) -> bool:
        """
        检查系统是否拥挤
        可用内存低于20%（或已用超过80%）时视为拥挤
        """
        available_percent = self._get_available_memory_percent()
        return available_percent < 20
    
    def get_max_allowed_sessions(self) -> int:
        """
        获取当前允许的最大会话数
        根据系统内存动态调整
        """
        if self._is_system_congested():
            # 系统拥挤，只允许1个新用户进入
            return 1
        return self.MAX_TOTAL_SESSIONS
    
    def _cleanup_zombie_sessions(self) -> list:
        """
        清理僵尸会话
        分级心跳超时策略：
        1. waiting（排队中）状态：如果 (当前时间 - last_ping > 10秒)，立即判定为僵尸并剔除
        2. active（活跃中）状态：如果 (当前时间 - last_ping > 30秒)，判定为僵尸并剔除，维持 is_busy 的豁免权
        硬锁定逻辑：
        - 只要该 Session ID 的 last_ping 在有效时间内，无论其 is_busy 是 True 还是 False，该名额禁止被任何新用户抢占
        发呆保护：
        - 活跃用户超过 10分钟 没有 is_busy 动作且没有心跳更新以外的交互，将其强制移出
        返回被清理的会话ID列表
        
        注意：此方法必须在已获取 self._session_lock 的情况下调用
        """
        current_time = time.time()
        zombies_to_remove = []
        
        for session_id, session_info in list(self._sessions.items()):
            # 详细日志
            print(f"[清理逻辑] 检查会话 {session_id}: 状态={session_info['status']}, 心跳时间={session_info['last_ping']}, 忙碌状态={session_info['is_busy']}")
            
            # 如果会话忙碌，为其代发心跳
            if session_info["is_busy"]:
                session_info["last_ping"] = current_time  # 心跳代理
                print(f"[清理逻辑] 会话 {session_id} 忙碌，代为更新心跳至 {current_time}")
                continue  # 绝对不删除忙碌的会话
            
            # 分级心跳超时检查
            if session_info["status"] == self.STATUS_WAITING:
                # 排队中用户：20秒超时（增加容错缓冲，防止网络抖动导致误判）
                if current_time - session_info["last_ping"] > 20:
                    zombies_to_remove.append(session_id)
                    del self._sessions[session_id]
                    print(f"[会话管理] 剔除排队僵尸: ID={session_id}, 最后心跳时间={session_info['last_ping']}, 当前时间={current_time}")
            elif session_info["status"] == self.STATUS_ACTIVE:
                # 活跃用户：30秒超时
                if current_time - session_info["last_ping"] > 30:
                    # 发呆保护：活跃用户超过10分钟没有忙碌动作且没有其他交互
                    last_active_time = session_info.get("busy_start_time", session_info["entry_time"])
                    if (current_time - last_active_time > 600):  # 10分钟
                        zombies_to_remove.append(session_id)
                        del self._sessions[session_id]
                        print(f"[会话管理] 活跃用户 {session_id} 发呆超过10分钟，强制移出")
                    else:
                        zombies_to_remove.append(session_id)
                        del self._sessions[session_id]
                        print(f"[会话管理] 剔除僵尸活跃者: {session_id} (30s超时)")
        
        # 将被清理的会话ID添加到expired_ids集合中
        if zombies_to_remove:
            with self._expired_ids_lock:
                self._expired_ids.update(zombies_to_remove)
                # 启动一个线程来在1分钟后自动移除这些ID
                threading.Thread(target=self._remove_expired_ids_after_timeout, args=(zombies_to_remove,), daemon=True).start()
        
        return zombies_to_remove
    
    def request_entry(self, session_id=None) -> bool:
        """
        请求进入系统 - 原子化实现
        原子化流程：
        1. 扫描所有 active 用户，只有 (now - last_ping > 30) 且 is_busy == False 的人才被标记为 expired 并移除
        2. 计算当前 active 且未过期的总人数
        3. 仅当 当前人数 < MAX_TOTAL_SESSIONS 时，才按照 entry_time 顺序提拔 waiting 队列中的第一名
        返回True表示成功进入，False表示需要排队
        """
        # 生成会话ID（如果没有提供）
        if session_id is None:
            session_id = str(uuid.uuid4())
        
        current_time = time.time()
        zombies_removed = []
        
        # 原子化操作：使用锁包装整个清理+检查+晋升流程
        with self._session_lock:
            # 第一步：扫描并清理过期用户，实现分级心跳超时逻辑
            for s_id, s_info in list(self._sessions.items()):
                # 如果会话忙碌，为其代发心跳
                if s_info["is_busy"]:
                    s_info["last_ping"] = current_time  # 心跳代理
                    print(f"[原子化清理] 会话 {s_id} 忙碌，代为更新心跳至 {current_time}")
                    continue  # 绝对不删除忙碌的会话
                
                # 分级心跳超时检查
                if s_info["status"] == self.STATUS_WAITING:
                    # 排队中用户：20秒超时（增加容错缓冲，防止网络抖动导致误判）
                    if current_time - s_info["last_ping"] > 20:
                        zombies_removed.append(s_id)
                        del self._sessions[s_id]
                        print(f"[会话管理] 剔除排队僵尸: ID={s_id}, 最后心跳时间={s_info['last_ping']}, 当前时间={current_time}")
                elif s_info["status"] == self.STATUS_ACTIVE:
                    # 活跃用户：30秒超时
                    if current_time - s_info["last_ping"] > 30:
                        # 发呆保护：活跃用户超过10分钟没有忙碌动作且没有其他交互
                        last_active_time = s_info.get("busy_start_time", s_info["entry_time"])
                        if (current_time - last_active_time > 600):  # 10分钟
                            zombies_removed.append(s_id)
                            del self._sessions[s_id]
                            print(f"[会话管理] 活跃用户 {s_id} 发呆超过10分钟，强制移出")
                        else:
                            zombies_removed.append(s_id)
                            del self._sessions[s_id]
                            print(f"[会话管理] 剔除僵尸活跃者: {s_id} (30s超时)")
            
            # 第二步：计算当前active且未过期的总人数
            max_allowed = self.get_max_allowed_sessions()
            active_count = sum(1 for s in self._sessions.values() if s["status"] == self.STATUS_ACTIVE)
            
            # 确保当前用户在会话列表中
            if session_id not in self._sessions:
                # 新用户，加入等待队列
                self._sessions[session_id] = {
                    "status": self.STATUS_WAITING,
                    "last_ping": current_time,
                    "is_busy": False,
                    "entry_time": current_time
                }
                print(f"[会话管理] 新用户 {session_id} 加入等待队列")
            else:
                # 老用户，更新心跳
                self._sessions[session_id]["last_ping"] = current_time
                print(f"[会话管理] 老用户 {session_id} 心跳更新")
            
            # 第三步：检查是否有可用名额，仅提拔waiting队列中的第一名
            available_slots = max_allowed - active_count
            if available_slots > 0:
                # 获取所有waiting状态的用户，按entry_time排序
                waiting_users = [(s_id, s_info) for s_id, s_info in self._sessions.items() 
                               if s_info["status"] == self.STATUS_WAITING]
                
                if waiting_users:
                    # 按entry_time升序排序（最早的排在前面）
                    waiting_users_sorted = sorted(waiting_users, key=lambda x: x[1]["entry_time"])
                    # 只提拔队列中的第一名
                    waiting_session_id, waiting_session_info = waiting_users_sorted[0]
                    # 将waiting用户晋升为active
                    self._sessions[waiting_session_id]["status"] = self.STATUS_ACTIVE
                    self._sessions[waiting_session_id]["last_ping"] = current_time
                    print(f"[原子化晋升] 会话 {waiting_session_id} 已从排队中晋升为活跃状态")
            
            # 检查当前用户的状态
            current_status = self._sessions[session_id]["status"]
            
            # 打印诊断日志
            active_sessions = [s_id for s_id, s in self._sessions.items() if s["status"] == self.STATUS_ACTIVE]
            waiting_sessions = [s_id for s_id, s in self._sessions.items() if s["status"] == self.STATUS_WAITING]
            print(f"[会话管理] 当前活跃 Session IDs: {active_sessions}")
            print(f"[会话管理] 当前排队 Session IDs: {waiting_sessions}")
            if zombies_removed:
                print(f"[会话管理] 已剔除僵尸会话: {zombies_removed}")
            print(f"[会话管理] 当前 {len(active_sessions)}/{max_allowed} 人在线")
            
            # 返回当前用户是否为active状态
            return current_status == self.STATUS_ACTIVE
    
    def update_ping(self, session_id) -> bool:
        """
        更新会话心跳
        返回True表示更新成功，False表示会话不存在
        """
        with self._session_lock:
            if session_id in self._sessions:
                # 只更新last_ping字段，保留status信息
                self._sessions[session_id]["last_ping"] = time.time()
                # 打印诊断日志
                print(f"[会话管理] 会话 {session_id} 心跳更新成功")
                return True
            return False
    
    def release_session(self, session_id=None) -> bool:
        """
        释放会话资源
        返回True表示释放成功，False表示会话不存在
        """
        if session_id is None:
            return False
            
        with self._session_lock:
            if session_id in self._sessions:
                del self._sessions[session_id]
                # 打印诊断日志
                active_sessions = list(self._sessions.keys())
                print(f"[会话管理] 会话 {session_id} 已释放")
                print(f"[会话管理] 当前活跃 Session IDs: {active_sessions}")
                return True
            return False
    
    def get_current_sessions(self) -> int:
        """
        获取当前活跃会话数
        """
        with self._session_lock:
            return sum(1 for s in self._sessions.values() if s["status"] == self.STATUS_ACTIVE)
    
    def get_available_slots(self) -> int:
        """
        获取当前可用的会话槽位数
        """
        with self._session_lock:
            max_allowed = self.get_max_allowed_sessions()
            active_count = sum(1 for s in self._sessions.values() if s["status"] == self.STATUS_ACTIVE)
            return max(0, max_allowed - active_count)
    
    def get_session_ids(self) -> list:
        """
        获取所有活跃会话ID列表
        """
        with self._session_lock:
            return [session_id for session_id, session_info in self._sessions.items() 
                    if session_info["status"] == self.STATUS_ACTIVE]
    
    def get_all_session_ids(self) -> list:
        """
        获取所有会话ID列表（包括活跃和排队的）
        """
        with self._session_lock:
            return list(self._sessions.keys())
    
    def get_waiting_session_ids(self) -> list:
        """
        获取所有排队会话ID列表
        """
        with self._session_lock:
            return [session_id for session_id, session_info in self._sessions.items() 
                    if session_info["status"] == self.STATUS_WAITING]
    
    def get_queue_position(self, session_id) -> int:
        """
        获取用户在排队队列中的位次
        返回0表示不在队列中，1表示第一个，2表示第二个，以此类推
        """
        with self._session_lock:
            # 检查用户是否存在
            if session_id not in self._sessions:
                return 0
            
            # 检查用户是否在等待队列中
            if self._sessions[session_id]["status"] != self.STATUS_WAITING:
                return 0
            
            # 获取所有waiting状态的用户，按entry_time排序
            waiting_users = [(s_id, s_info) for s_id, s_info in self._sessions.items() 
                           if s_info["status"] == self.STATUS_WAITING]
            
            # 按entry_time升序排序（最早的排在前面）
            waiting_users_sorted = sorted(waiting_users, key=lambda x: x[1]["entry_time"])
            
            # 查找当前用户的位置
            for i, (waiting_id, _) in enumerate(waiting_users_sorted):
                if waiting_id == session_id:
                    # 返回位次（从1开始）
                    return i + 1
            
            # 不应该到达这里
            return 0
    
    def check_current_status(self, session_id) -> str:
        """
        检查当前会话的状态
        返回：Active（在线）、Waiting（排队）、New（完全新的会话）或 Expired（已过期）
        """
        # 先检查过期ID，避免不必要的会话锁获取
        with self._expired_ids_lock:
            if session_id in self._expired_ids:
                print(f"[状态检查] 会话 {session_id} 在过期记录中，返回 Expired")
                return self.STATUS_EXPIRED
        
        with self._session_lock:
            if session_id in self._sessions:
                status = self._sessions[session_id]["status"]
                print(f"[状态检查] 会话 {session_id} 在会话列表中，状态为 {status}")
                return status.capitalize()  # 返回 Active 或 Waiting
        
        print(f"[状态检查] 会话 {session_id} 不在任何列表中，返回 New")
        return self.STATUS_NEW
    
    def _remove_expired_ids_after_timeout(self, session_ids):
        """
        在指定时间后从expired_ids集合中移除会话ID
        """
        time.sleep(self._EXPIRED_IDS_TTL)
        with self._expired_ids_lock:
            for session_id in session_ids:
                if session_id in self._expired_ids:
                    self._expired_ids.remove(session_id)
                    print(f"[会话管理] 会话 {session_id} 已从过期记录中清除")
    
    def _monitor_loop(self):
        """
        后台监控循环，定期清理僵尸会话并尝试晋升排队用户
        """
        import random
        while True:
            try:
                with self._session_lock:
                    zombies = self._cleanup_zombie_sessions()
                    # 尝试晋升排队用户
                    self._try_promote()
                
                # 记录监控日志
                current_time = time.strftime("%Y-%m-%d %H:%M:%S")
                active_count = self.get_current_sessions()
                waiting_count = len(self.get_waiting_session_ids())
                print(f"[{current_time}] [后台监控] 活跃:{active_count}, 排队:{waiting_count}, 已清理:{len(zombies)}")
                
                # 等待10-20秒（随机化避免资源竞争）
                time.sleep(10 + random.randint(0, 10))
            except Exception as e:
                print(f"[后台监控线程错误] {e}")
                time.sleep(5)  # 出错后短时间重试
    
    def _try_promote(self):
        """
        尝试将排队中的用户晋升为活跃状态
        """
        current_time = time.time()
        max_allowed = self.get_max_allowed_sessions()
        active_count = sum(1 for s in self._sessions.values() if s["status"] == self.STATUS_ACTIVE)
        available_slots = max_allowed - active_count
        
        if available_slots > 0:
            # 获取所有waiting状态的用户，按entry_time排序
            waiting_users = [(s_id, s_info) for s_id, s_info in self._sessions.items() 
                           if s_info["status"] == self.STATUS_WAITING]
            
            if waiting_users:
                # 按entry_time升序排序（最早的排在前面）
                waiting_users_sorted = sorted(waiting_users, key=lambda x: x[1]["entry_time"])
                # 只提拔队列中的前available_slots名
                for i in range(min(available_slots, len(waiting_users_sorted))):
                    waiting_session_id, waiting_session_info = waiting_users_sorted[i]
                    # 将waiting用户晋升为active
                    self._sessions[waiting_session_id]["status"] = self.STATUS_ACTIVE
                    self._sessions[waiting_session_id]["last_ping"] = current_time
                    print(f"[原子化晋升] 会话 {waiting_session_id} 已从排队中晋升为活跃状态")
    
    def set_busy_status(self, session_id, is_busy) -> bool:
        """
        设置会话的忙碌状态
        返回True表示设置成功，False表示会话不存在
        """
        with self._session_lock:
            if session_id in self._sessions:
                self._sessions[session_id]["is_busy"] = is_busy
                # 记录进入忙碌状态的时间
                if is_busy:
                    self._sessions[session_id]["busy_start_time"] = time.time()
                print(f"[会话管理] 会话 {session_id} 忙碌状态设置为: {is_busy}")
                return True
            return False

# 使用Streamlit的cache_resource确保全局唯一实例
@st.cache_resource
def get_session_manager():
    return GlobalSessionManager()

# 获取Session ID的辅助函数
from streamlit.runtime.scriptrunner import get_script_run_ctx

def get_session_id():
    ctx = get_script_run_ctx()
    if ctx is None:
        return None
    return ctx.session_id
