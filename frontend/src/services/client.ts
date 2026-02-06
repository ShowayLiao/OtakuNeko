const BASE_URL = 'http://localhost:8000/api/v1';

// 简单的 fetch 封装
export const request = async <T>(endpoint: string, options: RequestInit = {}): Promise<T> => {
  // 1. 自动从 localStorage 拿 Token
  const token = localStorage.getItem('token');
  
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  // 2. 发起请求
  const response = await fetch(`${BASE_URL}${endpoint}`, {
    ...options,
    headers,
  });

  // 3. 统一处理 HTTP 错误
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `请求失败: ${response.status}`);
  }

  // 4. 返回数据
  return response.json();
};
