# src/vector_store.py
import json
import os
import time
import numpy as np
import pickle
from sentence_transformers import SentenceTransformer

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# 路径定义
DATA_DIR = "data/datasets"
INDEX_DIR = "data/vector_index"
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2" # 支持多语言(中英日)的轻量模型

class LocalVectorStore:
    def __init__(self):
        self.embeddings = None
        self.metadata = [] # 存储向量ID对应的动画详细信息
        self.model = None
        
        # Cache for search results
        self._search_cache = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._last_cache_cleanup = time.time()
        
        # 确保目录存在
        if not os.path.exists(INDEX_DIR):
            os.makedirs(INDEX_DIR)
            
    def _load_model(self, log_func=print):
        """懒加载模型 (第一次用到时才加载，节省内存)"""
        if self.model is None:
            log_func("📥 正在加载 Embedding 模型 (首次运行可能需要下载)...")
            self.model = SentenceTransformer(MODEL_NAME)

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

    def build_index(self, log_func=print):
        """
        log_func: 前端传进来的更新函数
        """
        self._load_model(log_func)
        
        candidates = []
        # 读取已看
        path_watched = os.path.join(DATA_DIR, "dataset_watched.json")
        if os.path.exists(path_watched):
            with open(path_watched, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item['_source'] = 'Watched'
                    candidates.append(item)
                    
        # 读取抛弃
        path_dropped = os.path.join(DATA_DIR, "dataset_dropped.json")
        if os.path.exists(path_dropped):
            with open(path_dropped, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for item in data:
                    item['_source'] = 'Dropped'
                    candidates.append(item)
        
        if not candidates:
            return "⚠️ 没有找到 dataset 数据。"

        log_func(f"🔄 检测到 {len(candidates)} 条数据，正在进行文本预处理...")

        # 准备 texts
        texts = [self._prepare_text(item) for item in candidates]
        
        log_func(f"🚀 开始向量化运算 (0/{len(texts)})...")
        
        # 关掉 show_progress_bar (因为它只打印在黑窗口，网页看不见，还会造成卡顿假象)
        embeddings = self.model.encode(texts, show_progress_bar=False) 
        
        log_func("✅ 向量化运算完成！正在转换数据格式...")
        embeddings = np.array(embeddings).astype('float32')
        
        log_func("💾 正在保存向量数据和元数据到磁盘...")
        
        # 保存向量和元数据
        with open(os.path.join(INDEX_DIR, "anime_embeddings.pkl"), 'wb') as f:
            pickle.dump(embeddings, f)
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

    def load_index(self):
        """
        从磁盘加载索引。
        逻辑：优先读取本地文件 -> 如果读取失败（文件不存在或损坏） -> 自动触发构建流程。
        """
        embed_path = os.path.join(INDEX_DIR, "anime_embeddings.pkl")
        meta_path = os.path.join(INDEX_DIR, "anime_meta.pkl")

        try:
            # --- 尝试加载阶段 ---
            if not os.path.exists(embed_path) or not os.path.exists(meta_path):
                raise FileNotFoundError("索引文件缺失")

            with open(embed_path, 'rb') as f:
                self.embeddings = pickle.load(f)
            with open(meta_path, 'rb') as f:
                self.metadata = pickle.load(f)
            
            # print("✅ 本地索引加载成功") # 可选日志
            return True

        except Exception as e:
            # --- 自动构建阶段 ---
            print(f"⚠️ 未检测到有效索引 ({e})，正在自动构建...")
            
            try:
                # 调用 build_index
                # 注意：这里 log_func 传入 print，将进度打印到控制台，避免 UI 报错
                self.build_index(log_func=print)
                print("✅ 自动索引构建完成")
                return True
            except Exception as build_e:
                print(f"❌ 致命错误：索引自动构建失败: {build_e}")
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

    def search(self, query_text, top_k=20):
        """
        搜索方法使用numpy实现的余弦相似度计算
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
        
        if self.embeddings is None:
            if not self.load_index(): return []
        
        self._load_model()
        
        # 1. 向量化查询词
        query_vector = self.model.encode([query_text])
        query_vector = np.array(query_vector).astype('float32')
        
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

# 全局单例
vector_store = LocalVectorStore()