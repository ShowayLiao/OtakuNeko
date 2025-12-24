"use client";

import { Card } from '@/components/ui/Card';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';

// Mock数据
const lineData1 = [
  { name: 'Mon', value: 400 },
  { name: 'Tue', value: 300 },
  { name: 'Wed', value: 500 },
  { name: 'Thu', value: 400 },
  { name: 'Fri', value: 600 },
];

const lineData2 = [
  { name: 'Mon', value: 200 },
  { name: 'Tue', value: 250 },
  { name: 'Wed', value: 300 },
  { name: 'Thu', value: 350 },
  { name: 'Fri', value: 400 },
];

const pieData = [
  { name: 'Task A', value: 400 },
  { name: 'Task B', value: 300 },
  { name: 'Task C', value: 300 },
  { name: 'Task D', value: 200 },
];

const COLORS = ['#8b5cf6', '#3b82f6', '#10b981', '#f59e0b'];

interface AnalysisInsightsProps {
  totalSubjects: number;
  totalCollections: number;
}

export const AnalysisInsights: React.FC<AnalysisInsightsProps> = ({ totalSubjects, totalCollections }) => {
  return (
    <Card>
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-900">AI Analysis Insights</h2>
      </div>
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* 左侧：折线图和数据指标 */}
        <div className="space-y-6">
          {/* 第一个折线图 */}
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineData1}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="name" stroke="#e5e7eb" />
                <YAxis stroke="#e5e7eb" />
                <Line type="monotone" dataKey="value" stroke="#8b5cf6" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          
          {/* 第二个折线图 */}
          <div className="h-40">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={lineData2}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f3f4f6" />
                <XAxis dataKey="name" stroke="#e5e7eb" />
                <YAxis stroke="#e5e7eb" />
                <Line type="monotone" dataKey="value" stroke="#3b82f6" strokeWidth={2} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          
          {/* 数据指标 */}
          <div className="grid grid-cols-3 gap-4">
            {
              [
                { label: 'Total Anime/Books', value: totalSubjects.toString(), color: 'text-purple-600' },
                { label: 'Total Collections', value: totalCollections.toString(), color: 'text-blue-500' },
                { label: 'Efficiency', value: '95%', color: 'text-green-600' },
              ].map((item, index) => (
                <div key={index} className="text-center">
                  <div className="text-2xl font-bold mb-1">{item.value}</div>
                  <div className="text-sm text-gray-600">{item.label}</div>
                </div>
              ))
            }
          </div>
        </div>
        
        {/* 右侧：环形图 */}
        <div className="flex items-center justify-center">
          <div className="h-80 w-80">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  fill="#8884d8"
                  paddingAngle={5}
                  dataKey="value"
                >
                  {pieData.map((entry, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </Card>
  );
};
