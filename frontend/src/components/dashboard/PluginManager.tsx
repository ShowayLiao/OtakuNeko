"use client";

import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';
import { Switch } from '@/components/ui/Switch';
import { Bot, Code, Layers, Settings } from 'lucide-react';
import { useState } from 'react';

// Mock数据
const plugins = [
  { id: 1, name: 'AI Agents', version: 'v1.2.3', icon: <Bot className="h-5 w-5 text-purple-600" />, enabled: true },
  { id: 2, name: 'Plugin Ovisane', version: 'v2.0.1', icon: <Code className="h-5 w-5 text-blue-500" />, enabled: false },
  { id: 3, name: 'Plugin Min', version: 'v0.9.8', icon: <Layers className="h-5 w-5 text-green-600" />, enabled: true },
  { id: 4, name: 'Settings Manager', version: 'v1.5.2', icon: <Settings className="h-5 w-5 text-gray-600" />, enabled: false },
];

export const PluginManager: React.FC = () => {
  const [pluginList, setPluginList] = useState(plugins);
  
  const togglePlugin = (id: number) => {
    setPluginList(prev => 
      prev.map(plugin => 
        plugin.id === id ? { ...plugin, enabled: !plugin.enabled } : plugin
      )
    );
  };
  
  return (
    <Card>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold text-gray-900">Plugin Manager</h2>
        <Button variant="outline">Installed plugin</Button>
      </div>
      
      {/* Plugin List */}
      <div className="space-y-4">
        {pluginList.map(plugin => (
          <div key={plugin.id} className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50">
            <div className="flex items-center gap-3">
              {plugin.icon}
              <div>
                <div className="font-medium">{plugin.name}</div>
                <div className="text-sm text-gray-500">{plugin.version}</div>
              </div>
            </div>
            <Switch 
              checked={plugin.enabled} 
              onChange={() => togglePlugin(plugin.id)} 
            />
          </div>
        ))}
      </div>
    </Card>
  );
};
