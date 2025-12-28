"use client";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
  variant?: 'default' | 'outline' | 'link';
  size?: 'default' | 'icon' | 'sm';
}

export const Button: React.FC<ButtonProps> = ({ 
  children, 
  variant = 'default', 
  size = 'default',
  className = '',
  ...props 
}) => {
  const variantStyles = {
    default: 'bg-primary text-primary-foreground hover:bg-primary/90',
    outline: 'bg-transparent border border-gray-300 text-gray-700 hover:bg-gray-50 dark:border-gray-600 dark:text-gray-300 dark:hover:bg-gray-800',
    link: 'bg-transparent text-primary hover:text-primary/80 hover:underline p-0 h-auto font-normal'
  };
  
  const sizeStyles = {
    default: 'px-4 py-2',
    icon: 'w-10 h-10 p-0',
    sm: 'px-3 py-1.5 text-sm'
  };
  
  return (
    <button
      className={`flex items-center justify-center rounded-lg font-medium transition-colors ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
};
