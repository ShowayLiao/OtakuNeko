"use client";

interface ButtonProps {
  children: React.ReactNode;
  variant?: 'default' | 'outline';
  className?: string;
  onClick?: () => void;
}

export const Button: React.FC<ButtonProps> = ({ 
  children, 
  variant = 'default', 
  className = '',
  onClick
}) => {
  const variantStyles = {
    default: 'bg-purple-600 text-white hover:bg-purple-700',
    outline: 'bg-transparent border border-gray-300 text-gray-700 hover:bg-gray-50'
  };
  
  return (
    <button
      className={`rounded-lg px-4 py-2 font-medium transition-colors ${variantStyles[variant]} ${className}`}
      onClick={onClick}
    >
      {children}
    </button>
  );
};
