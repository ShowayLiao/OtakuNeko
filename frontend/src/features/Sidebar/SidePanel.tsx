import { DraggableSideNav } from '@lobehub/ui';
import { ReactNode } from 'react';

interface SidePanelProps {
  expand: boolean;
  width: number;
  onExpandChange: (expand: boolean) => void;
  onWidthChange: (_: any, width: number) => void;
  children: ReactNode;
  title?: string;
}

export const SidePanel = ({ children, title, ...props }: SidePanelProps) => {
  return (
    <DraggableSideNav
      placement="left"
      minWidth={200}
      maxWidth={400}
      header={title ? <div style={{ padding: 16, fontWeight: 'bold' }}>{title}</div> : null}
      body={(isExpanded) => <div style={{ padding: 16 }}>{children}</div>}
      {...props}
    />
  );
};
