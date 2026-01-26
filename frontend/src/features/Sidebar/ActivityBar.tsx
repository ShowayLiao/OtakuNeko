import { SideNav, Avatar, ActionIcon } from '@lobehub/ui';
import { MessageSquare, Grid, Wrench, UserCircle, Settings, PanelLeftClose, PanelLeftOpen } from 'lucide-react';

interface ActivityBarProps {
  activeKey: string;
  onChange: (key: string) => void;
  expand: boolean;
  onToggleExpand: () => void;
}

export const ActivityBar = ({ activeKey, onChange, expand, onToggleExpand }: ActivityBarProps) => {
  return (
    <SideNav
      avatar={<Avatar avatar="https://avatars.githubusercontent.com/u/17870709?v=4" size={40} />}
      topActions={
        <>
          <ActionIcon
            icon={MessageSquare}
            active={activeKey === 'chat'}
            onClick={() => onChange('chat')}
            size="large"
          />
          <ActionIcon
            icon={Grid}
            active={activeKey === 'collections'}
            onClick={() => onChange('collections')}
            size="large"
          />
          <ActionIcon
            icon={Wrench}
            active={activeKey === 'tools'}
            onClick={() => onChange('tools')}
            size="large"
          />
          <ActionIcon
            icon={UserCircle}
            active={activeKey === 'role'}
            onClick={() => onChange('role')}
            size="large"
          />
        </>
      }
      bottomActions={
        <>
          <ActionIcon
            icon={Settings}
            active={activeKey === 'settings'}
            onClick={() => onChange('settings')}
            size="large"
          />
          <ActionIcon
            icon={expand ? PanelLeftClose : PanelLeftOpen}
            onClick={onToggleExpand}
            size="large"
          />
        </>
      }
    />
  );
};
