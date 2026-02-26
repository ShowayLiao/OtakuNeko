import { NextResponse } from 'next/server';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const url = searchParams.get('url');

  if (!url) {
    return new NextResponse('Missing url parameter', { status: 400 });
  }

  try {
    // 关键：在这里伪造请求头，骗过豆瓣
    const response = await fetch(url, {
      headers: {
        'Referer': 'https://movie.douban.com/',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
      }
    });

    if (!response.ok) throw new Error('Fetch failed');

    // 把豆瓣的图片数据流直接转发给前端
    const buffer = await response.arrayBuffer();
    return new NextResponse(buffer, {
      headers: {
        'Content-Type': response.headers.get('Content-Type') || 'image/jpeg',
        'Cache-Control': 'public, max-age=864000', // 让浏览器缓存 10 天
      }
    });
  } catch (error) {
    return new NextResponse('Error fetching image', { status: 500 });
  }
}