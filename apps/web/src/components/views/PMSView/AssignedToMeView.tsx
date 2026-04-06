import { useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Task } from '@/src/types';
import { MOCK_TASKS } from '@/src/mockData';
import { ListView } from './ListView';
import { TaskDetail } from './TaskDetail';

export const AssignedToMeView = () => {
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);

  // Filter tasks assigned to "John Doe" (or any mock user)
  const assignedTasks = MOCK_TASKS.filter(task => task.assignee?.name === 'John Doe');

  return (
    <div className="h-full flex flex-col relative">
      <header className="bg-clickup-bg border-b border-clickup-border px-8 pt-6 pb-4">
        <h1 className="text-2xl font-bold text-clickup-text">Assigned to me</h1>
        <p className="text-gray-500 text-sm mt-1">Tasks assigned to you across all spaces</p>
      </header>

      <main className="flex-1 overflow-y-auto p-8 custom-scrollbar">
        <ListView tasks={assignedTasks} onSelectTask={setSelectedTask} />
      </main>

      <AnimatePresence>
        {selectedTask && (
          <>
            <motion.div 
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedTask(null)}
              className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
            />
            <TaskDetail task={selectedTask} onClose={() => setSelectedTask(null)} />
          </>
        )}
      </AnimatePresence>
    </div>
  );
};
