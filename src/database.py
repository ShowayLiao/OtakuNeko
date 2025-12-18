import sqlite3
import json
import os
import threading
from typing import Dict, List, Optional, Any
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    SQLite 数据库管理类，实现单例模式和线程安全的数据库连接
    """
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super(DatabaseManager, cls).__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = None):
        if self._initialized:
            return
            
        with self._lock:
            if self._initialized:
                return
                
            # 数据库路径默认在 data 目录下
            if db_path is None:
                db_path = os.path.join("data", "otaku_neko.db")
            
            self.db_path = db_path
            self._connection_cache = threading.local()
            self._initialized = True
            
            # 确保数据库目录存在
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
            
            # 初始化数据库表
            self._init_tables()
    
    def _get_connection(self) -> sqlite3.Connection:
        """
        为每个线程获取独立的数据库连接
        """
        if not hasattr(self._connection_cache, 'conn'):
            self._connection_cache.conn = sqlite3.connect(
                self.db_path,
                check_same_thread=False,  # 允许跨线程使用连接
                isolation_level=None  # 使用自动提交模式
            )
            # 启用外键约束
            self._connection_cache.conn.execute("PRAGMA foreign_keys = ON;")
        return self._connection_cache.conn
    
    def _init_tables(self):
        """
        初始化数据库表结构
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 创建用户表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 创建动漫记录表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bangumi_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bangumi_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT NOT NULL,
                score INTEGER DEFAULT 0,
                tags TEXT,  -- JSON 格式存储标签列表
                summary TEXT,
                image TEXT,
                updated_at TIMESTAMP NOT NULL,
                director TEXT,
                script TEXT,
                studio TEXT,
                cv TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                UNIQUE(user_id, bangumi_id)
            )
        ''')
        
        conn.commit()
        cursor.close()
    
    def get_user_id(self, username: str) -> Optional[int]:
        """
        获取用户 ID，如果不存在则创建
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # 查找用户
        cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        
        if user:
            user_id = user[0]
        else:
            # 创建新用户
            cursor.execute("INSERT INTO users (username) VALUES (?)", (username,))
            user_id = cursor.lastrowid
            conn.commit()
        
        cursor.close()
        return user_id
    
    def save_records(self, username: str, records: List[Dict]):
        """
        保存动漫记录到数据库
        """
        if not records:
            return
            
        conn = self._get_connection()
        cursor = conn.cursor()
        
        user_id = self.get_user_id(username)
        
        # 批量插入或更新记录
        for record in records:
            bangumi_id = record.get('id')
            if not bangumi_id:
                continue
            
            # 将标签列表转换为 JSON 字符串
            tags = json.dumps(record.get('tags', []), ensure_ascii=False)
            
            # 准备数据
            data = (
                user_id,
                bangumi_id,
                record.get('title', ''),
                record.get('type', 'anime'),
                record.get('status', ''),
                record.get('score', 0),
                tags,
                record.get('summary', ''),
                record.get('image', ''),
                record.get('updated_at', datetime.now().isoformat()),
                record.get('director', ''),
                record.get('script', ''),
                record.get('studio', ''),
                record.get('cv', '')
            )
            
            # 使用 INSERT OR REPLACE 实现更新功能
            cursor.execute('''
                INSERT OR REPLACE INTO bangumi_records (
                    user_id, bangumi_id, title, type, status, score, tags, 
                    summary, image, updated_at, director, script, studio, cv
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', data)
        
        conn.commit()
        cursor.close()
    
    def load_records(self, username: str) -> List[Dict]:
        """
        从数据库加载用户的动漫记录
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        user_id = self.get_user_id(username)
        
        # 查询所有记录
        cursor.execute(
            "SELECT bangumi_id, title, type, status, score, tags, summary, image, updated_at, director, script, studio, cv "
            "FROM bangumi_records WHERE user_id = ? ORDER BY updated_at DESC",
            (user_id,)
        )
        
        records = []
        for row in cursor.fetchall():
            # 将 JSON 字符串转换为标签列表
            tags = json.loads(row[5]) if row[5] else []
            
            record = {
                'id': row[0],
                'title': row[1],
                'type': row[2],
                'status': row[3],
                'score': row[4],
                'tags': tags,
                'summary': row[6],
                'image': row[7],
                'updated_at': row[8],
                'director': row[9],
                'script': row[10],
                'studio': row[11],
                'cv': row[12]
            }
            records.append(record)
        
        cursor.close()
        return records
    
    def migrate_from_json(self, username: str, json_file_path: str) -> bool:
        """
        从 JSON 文件迁移数据到数据库
        """
        if not os.path.exists(json_file_path):
            logger.warning(f"JSON 文件不存在: {json_file_path}")
            return False
            
        try:
            # 读取 JSON 数据
            with open(json_file_path, 'r', encoding='utf-8') as f:
                records = json.load(f)
            
            if not isinstance(records, list):
                logger.error(f"JSON 数据格式错误，期望列表类型: {json_file_path}")
                return False
            
            # 保存到数据库
            self.save_records(username, records)
            logger.info(f"成功从 {json_file_path} 迁移 {len(records)} 条记录到数据库")
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析错误: {e}")
            return False
        except Exception as e:
            logger.error(f"数据迁移失败: {e}")
            return False
    
    def close_connections(self):
        """
        关闭所有数据库连接
        """
        if hasattr(self._connection_cache, 'conn'):
            self._connection_cache.conn.close()
            delattr(self._connection_cache, 'conn')
    
    def __del__(self):
        """
        析构函数，确保连接关闭
        """
        self.close_connections()