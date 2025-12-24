"use client";

import React, { useState } from 'react';
import { Settings, ChevronDown, ChevronUp } from 'lucide-react';

interface Tool {
  id: string;
  name: string;
  enabled: boolean;
  description: string;
}

export const ToolsPanel: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);
  const [tools, setTools] = useState<Tool[]>([
    { id: 'bangumi-search', name: 'Bangumi Search', enabled: true, description: 'Search anime/manga information' },
    { id: 'calendar', name: 'Calendar', enabled: false, description: 'Manage your viewing schedule' },
    { id: 'memory', name: 'Memory', enabled: true, description: 'Store and retrieve past conversations' },
    { id: 'notes', name: 'Notes', enabled: false, description: 'Take and manage notes' },
  ]);

  const togglePanel = () => {
    setIsOpen(!isOpen);
  };

  const toggleTool = (toolId: string) => {
    setTools(prev => 
      prev.map(tool => 
        tool.id === toolId ? { ...tool, enabled: !tool.enabled } : tool
      )
    );
  };

  return (
    <div>
      {/* Panel Header */}
      <div
        onClick={togglePanel}
        className="flex items-center justify-between p-4 bg-gray-50/50 border-t border-gray-100 cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <Settings className="h-5 w-5 text-gray-500" />
          <span className="font-medium text-gray-900">Tools</span>
          <span className="text-xs text-gray-500">{tools.filter(t => t.enabled).length} enabled</span>
        </div>
        {isOpen ? <ChevronUp className="h-5 w-5 text-gray-500" /> : <ChevronDown className="h-5 w-5 text-gray-500" />}
      </div>

      {/* Panel Content */}
      {isOpen && (
        <div className="bg-gray-50/50 p-4">
          <div className="space-y-3">
            {tools.map((tool) => (
              <div key={tool.id} className="flex items-center justify-between p-3 rounded-lg hover:bg-gray-50 transition-colors">
                <div className="flex-1">
                  <div className="font-medium text-gray-900">{tool.name}</div>
                  <div className="text-xs text-gray-500 mt-1">{tool.description}</div>
                </div>
                <div className="ml-4">
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input
                      type="checkbox"
                      checked={tool.enabled}
                      onChange={() => toggleTool(tool.id)}
                      className="sr-only peer"
                    />
                    <div className={`w-11 h-6 rounded-full peer transition-colors duration-200 ${tool.enabled ? 'bg-purple-500' : 'bg-gray-200'}`}></div>
                    <div className={`absolute left-1 top-1 bg-white w-4 h-4 rounded-full peer-checked:translate-x-full transition-transform duration-200`}></div>
                  </label>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
