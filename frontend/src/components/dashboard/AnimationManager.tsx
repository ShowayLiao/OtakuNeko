"use client";

import { Card } from '@/components/ui/Card';
import { Button } from '@/components/ui/Button';

export const AnimationManager: React.FC = () => {
  return (
    <Card>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold text-gray-900">Animation Manager</h2>
        <Button variant="outline">Preview</Button>
      </div>
      
      {/* Preview Area */}
      <div className="bg-gray-100 rounded-xl h-48 mb-6 flex items-center justify-center">
        <span className="text-gray-500">Preview Area</span>
      </div>
      
      {/* Timeline */}
      <div className="relative h-24">
        {/* Timeline lines */}
        <div className="absolute top-0 left-0 right-0 h-px bg-gray-200"></div>
        <div className="absolute top-8 left-0 right-0 h-px bg-gray-200"></div>
        <div className="absolute top-16 left-0 right-0 h-px bg-gray-200"></div>
        
        {/* Keyframes */}
        <div className="absolute top-0 left-1/4 w-3 h-3 rounded-full bg-purple-600"></div>
        <div className="absolute top-8 left-1/2 w-3 h-3 rounded-full bg-purple-600"></div>
        <div className="absolute top-16 left-3/4 w-3 h-3 rounded-full bg-purple-600"></div>
        <div className="absolute top-0 left-1/3 w-3 h-3 rounded-full bg-blue-500"></div>
        <div className="absolute top-8 left-2/3 w-3 h-3 rounded-full bg-blue-500"></div>
      </div>
    </Card>
  );
};
