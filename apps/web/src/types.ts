export interface Task {
  id: string;
  name: string;
  status: 'TO DO' | 'IN PROGRESS' | 'REVIEW' | 'DONE';
  assignee?: { name: string, avatar: string };
  dueDate?: string;
  priority: 'URGENT' | 'HIGH' | 'NORMAL' | 'LOW' | 'NONE';
  comments: number;
  tags: string[];
  description?: string;
}
