"use client";

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, ResponsiveContainer } from 'recharts';

// Mock数据
const mockData = [
  { name: '00:00', value: 65 },
  { name: '02:00', value: 59 },
  { name: '04:00', value: 80 },
  { name: '06:00', value: 81 },
  { name: '08:00', value: 56 },
  { name: '10:00', value: 55 },
  { name: '12:00', value: 40 },
  { name: '14:00', value: 65 },
  { name: '16:00', value: 72 },
  { name: '18:00', value: 85 },
  { name: '20:00', value: 95 },
  { name: '22:00', value: 65 },
];

interface AICoreStatusProps {
  systemStatus: string;
}

export const AICoreStatus: React.FC<AICoreStatusProps> = ({ systemStatus }) => {
  return (
    <Card>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold text-gray-900">AI Core Status</h2>
        <Badge>{systemStatus}</Badge>
      </div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={mockData}>
            <defs>
              <linearGradient id="colorValue" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#8b5cf6" stopOpacity={0.8} />
                <stop offset="95%" stopColor="#8b5cf6" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <XAxis dataKey="name" stroke="#e5e7eb" />
            <YAxis stroke="#e5e7eb" />
            <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
            <Area 
              type="monotone" 
              dataKey="value" 
              stroke="#8b5cf6" 
              fillOpacity={1} 
              fill="url(#colorValue)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
};
