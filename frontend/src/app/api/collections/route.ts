import { NextResponse } from 'next/server';

// 后端 API 地址
const BACKEND_URL = 'http://127.0.0.1:8000';

export async function GET(request: Request) {
  try {
    // 从前端请求中获取查询参数
    const searchParams = new URL(request.url).searchParams;
    const backendUrl = new URL(`${BACKEND_URL}/api/v1/collections/`);
    
    // 1. 透传前端传来的所有参数 (limit, offset, type, status)
    searchParams.forEach((value, key) => {
      backendUrl.searchParams.append(key, value);
    });
    
    // 2. 验证 username 参数是否存在
    if (!backendUrl.searchParams.has('username')) {
      return NextResponse.json({ error: 'Username is required' }, { status: 400 });
    }
    
    console.log(`Proxying to Backend: ${backendUrl.toString()}`);
    
    // 调用后端 API
    const response = await fetch(backendUrl.toString());
    
    // 检查响应状态
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      console.error('Backend API Error:', response.status, errorData);
      throw new Error(`Backend API error: ${response.status} - ${JSON.stringify(errorData)}`);
    }
    
    // 获取后端返回的数据
    const collections = await response.json();
    
    console.log('Backend Response:', collections);
    
    return NextResponse.json(collections);
  } catch (error) {
    console.error('API Error:', error);
    return NextResponse.json({ error: 'Failed to fetch collections' }, { status: 500 });
  }
}