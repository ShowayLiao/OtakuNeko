/**
 * 图片配置辅助函数
 * 根据图片URL来源返回不同的配置，以优化加载性能并绕过防盗链限制
 */

export interface ImageConfig {
  unoptimized: boolean;
  referrerPolicy?: 'no-referrer' | 'origin' | 'unsafe-url';
}

/**
 * 根据图片URL返回正确的配置
 * 
 * 策略说明：
 * - 豆瓣图片 (doubanio.com): 
 *   - unoptimized=true: 避免Next.js服务端代理，让浏览器直连原图
 *   - referrerPolicy="no-referrer": 绕过豆瓣防盗链机制
 * 
 * - Bangumi图片 (lain.bgm.tv):
 *   - unoptimized=false: 保持Next.js图片优化性能
 *   - 不设置referrerPolicy: 使用默认行为
 * 
 * - 其他图片:
 *   - 使用默认配置
 * 
 * @param url - 图片URL
 * @returns 图片配置对象
 */
export function getImageProps(url: string): ImageConfig {
  if (!url) {
    return { unoptimized: false };
  }

  const isDouban = url.includes('doubanio.com');
  const isBangumi = url.includes('lain.bgm.tv');

  if (isDouban) {
    return {
      unoptimized: true,
      referrerPolicy: 'no-referrer'
    };
  }

  if (isBangumi) {
    return {
      unoptimized: false
    };
  }

  return {
    unoptimized: false
  };
}

/**
 * 检查图片是否来自豆瓣
 * @param url - 图片URL
 * @returns 是否为豆瓣图片
 */
export function isDoubanImage(url: string): boolean {
  return url?.includes('doubanio.com') || false;
}

/**
 * 检查图片是否来自Bangumi
 * @param url - 图片URL
 * @returns 是否为Bangumi图片
 */
export function isBangumiImage(url: string): boolean {
  return url?.includes('lain.bgm.tv') || false;
}
