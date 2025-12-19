# src/vector_store.py
import os
import time
import numpy as np
import pickle
import dashscope
import streamlit as st
from src.database import DatabaseManager

# 路径定义
INDEX_DIR = "data/vector_index"

# Custom exception for vector store issues
class VectorStoreError(Exception):
    """
    Exception raised when vector store operations fail.
    """
    pass

# 从环境变量或streamlit secrets中获取API Key
dashscope.api_key = st.secrets.get("DASHSCOPE_API_KEY") or os.getenv("DASHSCOPE_API_KEY")

if not dashscope.api_key:
    raise VectorStoreError("未配置DASHSCOPE_API_KEY环境变量")

class LocalVectorStore:
    def __init__(self, username="default_user"):
        self.embeddings = None
        self.metadata = [] # 存储向量ID对应的动画详细信息
        self.username = username
        
        # Cache for search results
        self._search_cache = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._last_cache_cleanup = time.time()
        
        # 确保目录存在
        if not os.path.exists(INDEX_DIR):
            os.makedirs(INDEX_DIR)

    def _prepare_text(self, item):
        """
        🚀 优化后的文本构造策略
        结构: [核心标签] + [标题] + [精简简介]
        """
        title = item.get('title', '未知')
        cv = item.get('cv', '未知配音')
        director = item.get('director', '未知导演')
        script = item.get('script', '未知脚本')

        # 1. 标签增强: 放在最前面，权重感最强
        # 将列表转为自然语言描述，模型更好理解
        tags = " ".join(item.get('tags', [])[:8]) # 只要前8个核心Tag
        
        # 2. 简介清洗与截断: 只取前 150 字，去除换行符噪音
        raw_summary = item.get('summary', '') or ""
        summary = raw_summary.replace("\n", " ").strip()[:150]
        
        # 3. 组合
        # 这种格式 "标签: ... 标题: ... 简介: ..." 对模型很友好
        text = f"风格标签: {tags}。 动画标题: {title}。 内容简介: {summary}。 配音演员: {cv}。 导演: {director}。 脚本: {script}。"
        
        return text
        
    def get_embeddings_api(self, texts):
        """
        调用dashscope API获取文本向量
        参数:
            texts: 文本列表
        返回:
            向量列表
        """
        try:
            response = dashscope.TextEmbedding.call(
                model='text-embedding-v2',
                input=texts
            )
            if response.status_code == 200:
                return [embedding['embedding'] for embedding in response.output['embeddings']]
            else:
                raise VectorStoreError(f"调用DashScope API失败: {response.message}")
        except Exception as e:
            raise VectorStoreError(f"获取向量失败: {str(e)}")

    def _fetch_data_from_db(self):
        """
        从数据库获取所有已同步的番剧数据
        """
        db_manager = DatabaseManager()  # 使用DatabaseManager单例
        records = db_manager.load_records(self.username)
        
        candidates = []
        for record in records:
            # 转换数据库记录为vector_store所需的格式
            item = {
                    'bangumi_id': record['id'],
                    'title': record['title'],
                    'type': record['type'],
                    'status': record['status'],
                    'score': record['score'],
                    'tags': record['tags'],
                    'summary': record['summary'],
                    'image': record['image'],
                    'updated_at': record['updated_at'],
                    'director': record['director'],
                    'script': record['script'],
                    'studio': record['studio'],
                    'cv': record['cv'],
                    '_source': record['status']  # 使用数据库中的status作为_source
                }
            candidates.append(item)
        
        return candidates

    def build_index(self, log_func=print):
        """
        log_func: 前端传进来的更新函数
        """
        # 从数据库获取数据
        candidates = self._fetch_data_from_db()
        
        if not candidates:
            return "⚠️ 数据库中没有找到番剧数据，请先进行Bangumi同步。"

        log_func(f"🔄 检测到 {len(candidates)} 条数据，正在进行文本预处理...")

        # 准备 texts
        texts = [self._prepare_text(item) for item in candidates]
        
        log_func(f"🚀 开始向量化运算 (0/{len(texts)})...")
        
        # 分批次处理，每批25条
        batch_size = 25
        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size
        
        for i in range(total_batches):
            start_idx = i * batch_size
            end_idx = min((i + 1) * batch_size, len(texts))
            batch_texts = texts[start_idx:end_idx]
            
            log_func(f"🔄 正在处理批次 {i+1}/{total_batches} ({start_idx+1}-{end_idx}/{len(texts)})")
            
            # 调用API获取向量
            batch_embeddings = self.get_embeddings_api(batch_texts)
            all_embeddings.extend(batch_embeddings)
        
        log_func("✅ 向量化运算完成！正在转换数据格式...")
        embeddings = np.array(all_embeddings).astype('float16')  # 使用float16节省存储空间
        
        log_func("💾 正在保存向量数据和元数据到磁盘...")
        
        # 保存向量和元数据
        # 使用.npy格式保存向量，更高效
        np.save(os.path.join(INDEX_DIR, "anime_embeddings.npy"), embeddings)
        # 元数据仍然使用pickle格式保存
        with open(os.path.join(INDEX_DIR, "anime_meta.pkl"), 'wb') as f:
            pickle.dump(candidates, f)
            
        # 更新内存
        self.embeddings = embeddings
        self.metadata = candidates
        
        success_msg = f"🎉 索引构建完成！共索引 {len(candidates)} 部动画。"
        log_func(success_msg)
        
        # Clear search cache when index is rebuilt
        self._search_cache.clear()
        
        return success_msg

    def load_index(self, log_func=print):
        """
        从磁盘加载索引。
        逻辑：优先读取本地文件 -> 如果读取失败（文件不存在或损坏） -> 自动触发构建流程。
        
        参数:
            log_func: 日志输出函数，默认为print
        """
        # 使用.npy格式读取向量
        embed_path = os.path.join(INDEX_DIR, "anime_embeddings.npy")
        meta_path = os.path.join(INDEX_DIR, "anime_meta.pkl")

        try:
            # --- 尝试加载阶段 ---
            if not os.path.exists(embed_path) or not os.path.exists(meta_path):
                raise FileNotFoundError("索引文件缺失")

            # 使用numpy加载.npy格式向量
            self.embeddings = np.load(embed_path)
            # 元数据仍然使用pickle格式读取
            with open(meta_path, 'rb') as f:
                self.metadata = pickle.load(f)
            
            # log_func("✅ 本地索引加载成功") # 可选日志
            return True

        except Exception as e:
            # --- 自动构建阶段 ---
            log_func(f"⚠️ 未检测到有效索引 ({e})，正在自动构建...")
            
            try:
                # 调用 build_index，传递日志函数
                self.build_index(log_func=log_func)
                log_func("✅ 自动索引构建完成")
                return True
            except Exception as build_e:
                log_func(f"❌ 致命错误：索引自动构建失败: {build_e}")
                import traceback
                traceback.print_exc()
                return False
            
            
    def _cleanup_cache(self):
        """清理过期的缓存"""
        current_time = time.time()
        if current_time - self._last_cache_cleanup < 60:  # Only cleanup every minute
            return
            
        expired_keys = []
        for key, (timestamp, _) in self._search_cache.items():
            if current_time - timestamp > self._cache_ttl:
                expired_keys.append(key)
        
        for key in expired_keys:
            del self._search_cache[key]
            
        self._last_cache_cleanup = current_time

    def search(self, query_text, top_k=20, log_func=print):
        """
        搜索方法使用numpy实现的余弦相似度计算
        
        参数:
            query_text: 查询文本
            top_k: 返回结果数量
            log_func: 日志输出函数，默认为print
        """
        # Check cache first
        cache_key = f"{query_text}_{top_k}"
        current_time = time.time()
        
        # Cleanup expired cache entries periodically
        self._cleanup_cache()
        
        if cache_key in self._search_cache:
            timestamp, cached_results = self._search_cache[cache_key]
            if current_time - timestamp < self._cache_ttl:
                return cached_results
        
        # 1. 检查向量库是否初始化
        if self.embeddings is None or len(self.metadata) == 0:
            # 2. 尝试从磁盘加载索引
            if not self.load_index(log_func=log_func):
                # 3. 如果加载失败，尝试构建新索引
                try:
                    build_result = self.build_index(log_func=log_func)
                    # 检查构建结果是否成功
                    if isinstance(build_result, str) and "没有找到" in build_result:
                        # 确认数据库是否真的为空
                        db_manager = DatabaseManager()
                        records = db_manager.load_records(self.username)
                        if not records:
                            raise VectorStoreError("由于本地暂无番剧数据，无法生成推荐。请先进行 Bangumi 数据同步。")
                        else:
                            raise VectorStoreError("构建索引失败，请重试。")
                except Exception as e:
                    # 检查数据库是否真的为空
                    db_manager = DatabaseManager()
                    records = db_manager.load_records(self.username)
                    if not records:
                        raise VectorStoreError("由于本地暂无番剧数据，无法生成推荐。请先进行 Bangumi 数据同步。")
                    else:
                        raise VectorStoreError(f"构建索引失败: {str(e)}")
            
            # 4. 检查构建/加载后是否有有效向量
            if self.embeddings is None or len(self.metadata) == 0:
                # 确认数据库是否真的为空
                db_manager = DatabaseManager()
                records = db_manager.load_records(self.username)
                if not records:
                    raise VectorStoreError("由于本地暂无番剧数据，无法生成推荐。请先进行 Bangumi 数据同步。")
                else:
                    raise VectorStoreError("构建索引失败，请重试。")
        
        # 1. 向量化查询词
        query_vector = self.get_embeddings_api([query_text])
        query_vector = np.array(query_vector).astype('float16')
        
        # 2. 计算余弦相似度
        # Normalize vectors for cosine similarity
        query_norm = query_vector / np.linalg.norm(query_vector)
        embeddings_norm = self.embeddings / np.linalg.norm(self.embeddings, axis=1, keepdims=True)
        
        # Calculate cosine similarities
        similarities = np.dot(embeddings_norm, query_norm.T).flatten()
        
        # 3. 获取Top-K最相似的结果
        top_indices = np.argsort(similarities)[::-1][:top_k]
        
        results = []
        for idx in top_indices:
            similarity = similarities[idx]
            
            # 过滤掉相似度过低的结果
            if similarity < 0.3:
                continue
            
            item = self.metadata[idx]
            
            # 数据清洗：只保留 LLM 需要的字段
            results.append({
                "title": item['title'],
                "status": item['_source'], # Watched / Dropped
                "score": item.get('score'),
                "tags": item.get('tags', [])[:5],
                "summary_snippet": (item.get('summary') or "")[:60] + "...",
                "similarity": float(similarity) # 相似度分数
            })
        
        # Cache the results
        self._search_cache[cache_key] = (current_time, results)
            
        return results

# 使用 @st.cache_resource 缓存 LocalVectorStore 实例
@st.cache_resource
def get_vector_store(username="default_user") -> LocalVectorStore:
    """
    使用 @st.cache_resource 缓存 LocalVectorStore 实例
    避免每次请求都重新创建向量存储实例
    
    参数:
    username: 用户名，用于从数据库获取对应用户的番剧数据
    """
    return LocalVectorStore(username)

# 获取全局单例（默认用户）
vector_store = get_vector_store()