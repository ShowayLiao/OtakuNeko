interface BadgeProps {
  children: React.ReactNode;
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({ children, className = '' }) => {
  return (
    <span className={`inline-flex items-center gap-1 bg-green-50 text-green-600 text-xs font-medium px-2 py-1 rounded-full ${className}`}>
      <span className="w-1.5 h-1.5 bg-green-600 rounded-full"></span>
      {children}
    </span>
  );
};
