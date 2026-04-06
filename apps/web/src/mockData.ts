import { Task } from './types';

export const PRIORITY_COLORS = {
  URGENT: 'text-red-500',
  HIGH: 'text-orange-500',
  NORMAL: 'text-blue-500',
  LOW: 'text-gray-500',
  NONE: 'text-gray-700'
};

export const STATUS_COLORS = {
  'TO DO': 'bg-gray-500',
  'IN PROGRESS': 'bg-blue-500',
  'REVIEW': 'bg-orange-500',
  'DONE': 'bg-green-500'
};

export const MOCK_TASKS: Task[] = [
  { id: '1', name: 'AI Platform Architecture Design', status: 'IN PROGRESS', assignee: { name: 'John Doe', avatar: 'JD' }, dueDate: 'Apr 10', priority: 'URGENT', comments: 12, tags: ['Design', 'Core', 'Project1'], description: 'Design the core architecture for the new AI platform.' },
  { id: '2', name: 'Patent Analysis Module Implementation', status: 'TO DO', assignee: { name: 'Jane Smith', avatar: 'JS' }, dueDate: 'Apr 15', priority: 'HIGH', comments: 5, tags: ['Dev', 'Patent', 'Project1'] },
  { id: '3', name: 'Internal Q&A Bot Frontend', status: 'REVIEW', assignee: { name: 'Bob Wilson', avatar: 'BW' }, dueDate: 'Apr 08', priority: 'NORMAL', comments: 8, tags: ['Frontend', 'Project2'] },
  { id: '4', name: 'Security Audit - Phase 1', status: 'DONE', assignee: { name: 'Alice Brown', avatar: 'AB' }, dueDate: 'Apr 01', priority: 'URGENT', comments: 20, tags: ['Security', 'Project2'] },
  { id: '5', name: 'User Feedback Collection', status: 'IN PROGRESS', assignee: { name: 'John Doe', avatar: 'JD' }, dueDate: 'Apr 12', priority: 'LOW', comments: 3, tags: ['Research', 'Project1'] },
  { id: '6', name: 'Documentation Update', status: 'TO DO', dueDate: 'Apr 20', priority: 'NONE', comments: 0, tags: ['Docs', 'Project2'] },
  { id: '7', name: 'API Integration Test', status: 'TO DO', assignee: { name: 'Jane Smith', avatar: 'JS' }, dueDate: 'Apr 22', priority: 'HIGH', comments: 2, tags: ['Dev', 'Project1'] },
  { id: '8', name: 'Mobile App UI Mockup', status: 'IN PROGRESS', assignee: { name: 'Bob Wilson', avatar: 'BW' }, dueDate: 'Apr 25', priority: 'NORMAL', comments: 4, tags: ['Design', 'Project2'] },
];
