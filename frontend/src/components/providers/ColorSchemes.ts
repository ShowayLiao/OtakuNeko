// 颜色方案定义，对应@lobehub/ui的customTheme类型
// 使用现有的三套主题颜色：default、ocean、sakura

// 亮色主题配置
const lightThemes = {
  default: {
    primaryColor: 'orange' as const, // 对应@lobehub/ui的PrimaryColors类型
    neutralColor: 'slate' as const, // 对应@lobehub/ui的NeutralColors类型
  },
  ocean: {
    primaryColor: 'blue' as const,
    neutralColor: 'slate' as const,
  },
  sakura: {
    primaryColor: 'magenta' as const,
    neutralColor: 'slate' as const,
  },
};

// 暗色主题配置
const darkThemes = {
  default: {
    primaryColor: 'orange' as const, // 橙色主题在暗色下保持活力
    neutralColor: 'slate' as const, // 深灰色调，提供更好的对比度
  },
  ocean: {
    primaryColor: 'cyan' as const, // 青色在暗色下更显清新
    neutralColor: 'slate' as const, // 深灰色调，保持一致性
  },
  sakura: {
    primaryColor: 'magenta' as const, // 洋红色在暗色下更显柔和
    neutralColor: 'slate' as const, // 深灰色调，提升可读性
  },
};

export { lightThemes, darkThemes };
