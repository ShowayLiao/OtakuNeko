import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // ---------------------------------------------------------
  // 1. 核心修改：开启 Standalone 模式
  // 这会让 Next.js 构建时自动分析依赖，只打包必要文件，大幅减小 Docker 体积
  // ---------------------------------------------------------
  output: "standalone",

  /* config options here */
  reactCompiler: true,
  
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'picsum.photos',
      },
      {
        protocol: 'https',
        hostname: 'lain.bgm.tv',
      },
      {
        protocol: 'https',
        hostname: '**.doubanio.com',
      },
    ],
  },

  // ---------------------------------------------------------
  // 2. 优化修改：API 地址动态化
  // 本地开发时默认连 localhost:8000
  // Docker 部署时，可以通过环境变量 API_PROXY_URL=http://backend:8000 来指定内部地址
  // ---------------------------------------------------------
  async rewrites() {
    const apiUrl = process.env.API_PROXY_URL || 'http://localhost:8000';
    
    console.log(`[Next.js Rewrite] Proxying /api to: ${apiUrl}`);
    
    return [
      {
        source: '/api/:path*',
        destination: `${apiUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;