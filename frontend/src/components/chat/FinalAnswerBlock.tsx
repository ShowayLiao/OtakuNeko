"use client";

interface FinalAnswerBlockProps {
  isStreaming: boolean;
  hasContent: boolean;
  children: React.ReactNode;
}

export default function FinalAnswerBlock({
  isStreaming,
  hasContent,
  children,
}: FinalAnswerBlockProps) {
  if (!hasContent && !isStreaming) return null;

  if (!hasContent && isStreaming) return null;

  return (
    <div className="w-full">
      {children}
    </div>
  );
}
