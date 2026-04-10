import { useState } from 'react';
import { Plus, Check, Trash2, Circle } from 'lucide-react';
import { cn } from '@/src/lib/utils';

interface Todo {
  id: string;
  text: string;
  completed: boolean;
}

export const PersonalListView = () => {
  const [todos, setTodos] = useState<Todo[]>([
    { id: '1', text: 'Review weekly report', completed: false },
    { id: '2', text: 'Prepare for team meeting', completed: true },
    { id: '3', text: 'Update project timeline', completed: false },
  ]);
  const [newTaskText, setNewTaskText] = useState('');

  const handleAddTodo = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTaskText.trim()) return;
    
    setTodos([
      ...todos,
      { id: Date.now().toString(), text: newTaskText.trim(), completed: false }
    ]);
    setNewTaskText('');
  };

  const toggleTodo = (id: string) => {
    setTodos(todos.map(todo => 
      todo.id === id ? { ...todo, completed: !todo.completed } : todo
    ));
  };

  const deleteTodo = (id: string) => {
    setTodos(todos.filter(todo => todo.id !== id));
  };

  return (
    <div className="h-full flex flex-col relative max-w-3xl mx-auto w-full">
      <header className="px-8 pt-10 pb-6">
        <h1 className="app-text-title-lg text-app-ink">Personal List</h1>
        <p className="app-text-body mt-2 text-gray-500">Your private to-do list</p>
      </header>

      <main className="flex-1 overflow-y-auto px-8 custom-scrollbar">
        <form onSubmit={handleAddTodo} className="mb-8 relative">
          <div className="absolute left-4 top-1/2 -translate-y-1/2 text-gray-400">
            <Plus size={18} />
          </div>
          <input
            type="text"
            value={newTaskText}
            onChange={(e) => setNewTaskText(e.target.value)}
            placeholder="Add a new task..."
            className="w-full bg-app-surface-sidebar border border-app-border rounded-lg py-3 pl-11 pr-4 text-app-ink focus:outline-none focus:border-app-accent transition-colors"
          />
        </form>

        <div className="space-y-2">
          {todos.map(todo => (
            <div 
              key={todo.id} 
              className={cn(
                "group flex items-center justify-between p-4 rounded-lg border transition-all",
                todo.completed 
                  ? "bg-app-surface-sidebar/50 border-transparent" 
                  : "bg-app-surface-sidebar border-app-border hover:border-gray-600"
              )}
            >
              <div className="flex items-center gap-4">
                <button 
                  onClick={() => toggleTodo(todo.id)}
                  className={cn(
                    "w-6 h-6 rounded-full flex items-center justify-center border transition-colors",
                    todo.completed 
                      ? "bg-green-500 border-green-500 text-white" 
                      : "border-gray-500 text-transparent hover:border-green-500"
                  )}
                >
                  {todo.completed ? <Check size={14} /> : <Circle size={14} className="opacity-0 group-hover:opacity-50 text-green-500" />}
                </button>
                <span className={cn(
                  "app-text-body transition-all",
                  todo.completed ? "text-gray-500 line-through" : "text-app-ink"
                )}>
                  {todo.text}
                </span>
              </div>
              <button 
                onClick={() => deleteTodo(todo.id)}
                className="text-gray-500 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity p-2"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
          {todos.length === 0 && (
            <div className="text-center py-12 text-gray-500">
              No tasks yet. Add one above!
            </div>
          )}
        </div>
      </main>
    </div>
  );
};
