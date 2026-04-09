import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  ChevronLeft, 
  ChevronRight, 
  Plus, 
  MessageSquare 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { SchedulePopover } from './SchedulePopover';

export const PlannerView = () => {
  const [viewMode, setViewMode] = useState<'Month' | 'Week' | 'Day'>('Month');
  const [selectedDate, setSelectedDate] = useState(20);
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
  const dates = Array.from({ length: 35 }, (_, i) => i - 3); // Mock dates for a month view
  const weekDates = [19, 20, 21, 22, 23, 24, 25]; // Mock dates for a week view

  const events = [
    { date: 12, title: 'AI Platform Sync', color: 'blue', startHour: 9, endHour: 10 },
    { date: 20, title: 'Patent Review', color: 'purple', startHour: 10, endHour: 11 },
    { date: 25, title: 'Team Lunch', color: 'green', startHour: 12, endHour: 13 },
  ];

  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ date: number, hour: number } | null>(null);
  const [dragEnd, setDragEnd] = useState<{ date: number, hour: number } | null>(null);
  const [popoverState, setPopoverState] = useState<{
    isOpen: boolean;
    position: { top: number; left: number };
    initialDate?: string;
    initialStartTime?: string;
    initialEndTime?: string;
  }>({ isOpen: false, position: { top: 0, left: 0 } });

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      if (isDragging) {
        setIsDragging(false);
      }
    };
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => window.removeEventListener('mouseup', handleGlobalMouseUp);
  }, [isDragging]);

  const handleDateClick = (e: React.MouseEvent, date: number) => {
    if (date > 0 && date <= 31) {
      if (viewMode === 'Month') {
        const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
        setPopoverState({
          isOpen: true,
          position: { top: rect.bottom + 10, left: Math.min(rect.left, window.innerWidth - 420) },
          initialDate: `May ${date}, 2024`,
          initialStartTime: '09:00 AM',
          initialEndTime: '10:00 AM',
        });
      } else {
        setSelectedDate(date);
        setViewMode('Day');
      }
    }
  };

  const formatHour = (h: number) => h === 12 ? '12:00 PM' : h > 12 ? `${h - 12}:00 PM` : `${h}:00 AM`;

  const handleMouseDown = (e: React.MouseEvent, date: number, hour: number) => {
    e.preventDefault(); // Prevent text selection
    setIsDragging(true);
    setDragStart({ date, hour });
    setDragEnd({ date, hour });
    setPopoverState(prev => ({ ...prev, isOpen: false }));
  };

  const handleMouseEnter = (date: number, hour: number) => {
    if (isDragging && dragStart && dragStart.date === date) {
      setDragEnd({ date, hour });
    }
  };

  const handleMouseUp = (e: React.MouseEvent) => {
    if (isDragging && dragStart && dragEnd) {
      setIsDragging(false);
      
      const startHour = Math.min(dragStart.hour, dragEnd.hour);
      const endHour = Math.max(dragStart.hour, dragEnd.hour) + 1;
      
      setPopoverState({
        isOpen: true,
        position: { top: e.clientY + 10, left: Math.min(e.clientX - 200, window.innerWidth - 420) },
        initialDate: `May ${dragStart.date}, 2024`,
        initialStartTime: formatHour(startHour),
        initialEndTime: formatHour(endHour),
      });
    }
  };

  const isCellSelected = (date: number, hour: number) => {
    if (!dragStart || !dragEnd) return false;
    if (dragStart.date !== date) return false;
    const minHour = Math.min(dragStart.hour, dragEnd.hour);
    const maxHour = Math.max(dragStart.hour, dragEnd.hour);
    return hour >= minHour && hour <= maxHour;
  };

  return (
    <motion.div 
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="p-8 h-full flex flex-col space-y-6 relative"
      ref={containerRef}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="app-text-title-lg text-clickup-text">Planner</h1>
          <div className="flex items-center bg-clickup-sidebar border border-clickup-border rounded-md p-1">
            {(['Month', 'Week', 'Day'] as const).map((mode) => (
              <button 
                key={mode}
                onClick={() => {
                  setViewMode(mode);
                  setPopoverState(prev => ({ ...prev, isOpen: false }));
                }}
                className={cn(
                  "app-text-control-sm rounded px-3 py-1 transition-all",
                  viewMode === mode 
                    ? "bg-clickup-hover text-clickup-text shadow-sm" 
                    : "text-gray-500 hover:text-clickup-text"
                )}
              >
                {mode}
              </button>
            ))}
          </div>
          <button 
            onClick={() => {
              setSelectedDate(20);
              setViewMode('Month');
            }}
            className="app-text-control-sm rounded-md border border-clickup-border px-3 py-1 text-gray-500 transition-colors hover:text-clickup-text"
          >
            Today
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 bg-clickup-sidebar border border-clickup-border rounded-md px-3 py-1.5">
            <ChevronLeft size={16} className="text-gray-500 cursor-pointer hover:text-clickup-text" />
            <span className="app-text-control px-2 text-clickup-text">
              {viewMode === 'Day' ? `May ${selectedDate}, 2024` : 'May 2024'}
            </span>
            <ChevronRight size={16} className="text-gray-500 cursor-pointer hover:text-clickup-text" />
          </div>
          <button className="app-text-control flex items-center gap-2 rounded-md bg-clickup-purple px-4 py-2 text-clickup-bg">
            <Plus size={16} />
            <span>Add Event</span>
          </button>
        </div>
      </div>

      <div className="flex-1 card p-0 overflow-hidden flex flex-col relative">
        <AnimatePresence mode="wait">
          {viewMode === 'Month' && (
            <motion.div 
              key="month"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="flex-1 flex flex-col"
            >
              <div className="grid grid-cols-7 border-b border-clickup-border">
                {days.map(day => (
                  <div key={day} className="app-text-overline border-r border-clickup-border py-2 text-center text-gray-500 last:border-r-0">
                    {day}
                  </div>
                ))}
              </div>
              <div className="flex-1 grid grid-cols-7 grid-rows-5">
                {dates.map((date, i) => (
                  <div 
                    key={i} 
                    onClick={(e) => handleDateClick(e, date)}
                    className={cn(
                      "p-2 border-r border-b border-clickup-border last:border-r-0 min-h-[100px] hover:bg-clickup-hover transition-colors cursor-pointer group",
                      (date < 1 || date > 31) && "bg-clickup-sidebar/50"
                    )}
                  >
                    <div className={cn(
                      "app-text-control-sm mb-2",
                      date === selectedDate ? "w-6 h-6 bg-clickup-purple text-clickup-bg rounded-full flex items-center justify-center -mt-1 -ml-1" : "text-gray-500"
                    )}>
                      {date > 0 && date <= 31 ? date : ''}
                    </div>
                    
                    {events.filter(e => e.date === date).map((event, idx) => (
                      <div key={idx} className={cn(
                        "app-text-micro mb-1 truncate border-l-2 px-1.5 py-0.5",
                        event.color === 'blue' && "bg-blue-500/20 border-blue-500 text-blue-400",
                        event.color === 'purple' && "bg-purple-500/20 border-purple-500 text-purple-400",
                        event.color === 'green' && "bg-green-500/20 border-green-500 text-green-400"
                      )}>
                        {event.title}
                      </div>
                    ))}
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {viewMode === 'Week' && (
            <motion.div 
              key="week"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <div className="flex border-b border-clickup-border">
                <div className="w-16 shrink-0"></div>
                <div className="flex-1 grid grid-cols-7">
                  {days.map((day, i) => (
                    <div 
                      key={day} 
                      onClick={() => {
                        setSelectedDate(weekDates[i]);
                        setViewMode('Day');
                      }}
                      className="py-3 text-center border-r border-clickup-border last:border-r-0 hover:bg-clickup-hover cursor-pointer transition-colors"
                    >
                      <div className="app-text-overline mb-1 text-gray-500">{day}</div>
                      <div className={cn(
                        "app-text-title-md font-bold",
                        weekDates[i] === selectedDate ? "text-clickup-purple" : "text-clickup-text"
                      )}>
                        {weekDates[i]}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto custom-scrollbar relative">
                {Array.from({ length: 12 }, (_, i) => i + 8).map(hour => (
                  <div key={hour} className="flex">
                    <div className="app-text-overline relative -top-3 w-16 shrink-0 py-2 pr-4 text-right text-gray-600">
                      {hour === 12 ? '12 PM' : hour > 12 ? `${hour - 12} PM` : `${hour} AM`}
                    </div>
                    <div className="flex-1 grid grid-cols-7">
                      {weekDates.map(date => (
                        <div 
                          key={`${date}-${hour}`}
                          className="border-t border-r border-clickup-border last:border-r-0 h-12 relative group"
                          onMouseDown={(e) => handleMouseDown(e, date, hour)}
                          onMouseEnter={() => handleMouseEnter(date, hour)}
                          onMouseUp={handleMouseUp}
                        >
                          {isCellSelected(date, hour) && (
                            <div className="absolute inset-0 bg-blue-500/20 border-x border-blue-500 z-10 pointer-events-none" />
                          )}
                          
                          {/* Render events */}
                          {events.filter(e => e.date === date && e.startHour === hour).map((event, idx) => (
                            <div key={idx} className={cn(
                              "app-text-micro absolute top-1 left-1 right-1 z-20 overflow-hidden rounded border-l-2 p-1.5 shadow-sm",
                              event.color === 'blue' && "bg-blue-500/10 border-blue-500 text-blue-400",
                              event.color === 'purple' && "bg-purple-500/10 border-purple-500 text-purple-400",
                              event.color === 'green' && "bg-green-500/10 border-green-500 text-green-400"
                            )}
                            style={{ height: `${(event.endHour - event.startHour) * 48 - 8}px` }}
                            >
                              <div className="font-bold truncate">{event.title}</div>
                              <div className="text-gray-500 truncate">{formatHour(event.startHour)}</div>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {viewMode === 'Day' && (
            <motion.div 
              key="day"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <div className="p-6 border-b border-clickup-border flex items-center gap-6">
                <div className="w-16 h-16 bg-clickup-purple rounded-xl flex flex-col items-center justify-center text-clickup-bg shadow-lg shadow-purple-500/20">
                  <span className="app-text-overline">May</span>
                  <span className="app-text-title-lg font-black">{selectedDate}</span>
                </div>
                <div>
                  <h2 className="app-text-title-lg text-clickup-text">
                    {days[weekDates.indexOf(selectedDate) !== -1 ? weekDates.indexOf(selectedDate) : 1]}day
                  </h2>
                  <p className="app-text-body text-gray-500">
                    You have {events.filter(e => e.date === selectedDate).length} event(s) scheduled for today.
                  </p>
                </div>
              </div>

              <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
                <div className="max-w-4xl mx-auto">
                  {Array.from({ length: 12 }, (_, i) => i + 8).map(hour => (
                    <div key={hour} className="flex group">
                      <div className="app-text-label relative -top-3 w-20 shrink-0 py-2 pr-6 text-right text-gray-600">
                        {hour === 12 ? '12 PM' : hour > 12 ? `${hour - 12} PM` : `${hour} AM`}
                      </div>
                      <div 
                        className="flex-1 border-t border-clickup-border h-16 relative"
                        onMouseDown={(e) => handleMouseDown(e, selectedDate, hour)}
                        onMouseEnter={() => handleMouseEnter(selectedDate, hour)}
                        onMouseUp={handleMouseUp}
                      >
                        {isCellSelected(selectedDate, hour) && (
                          <div className="absolute inset-0 bg-blue-500/20 border-x border-blue-500 z-10 pointer-events-none" />
                        )}
                        
                        {events.filter(e => e.date === selectedDate && e.startHour === hour).map((event, idx) => (
                          <div key={idx} className={cn(
                            "app-text-caption absolute top-2 left-2 right-4 z-20 rounded border-l-4 p-3 shadow-sm",
                            event.color === 'blue' && "bg-blue-500/10 border-blue-500 text-blue-400",
                            event.color === 'purple' && "bg-purple-500/10 border-purple-500 text-purple-400",
                            event.color === 'green' && "bg-green-500/10 border-green-500 text-green-400"
                          )}
                          style={{ height: `${(event.endHour - event.startHour) * 64 - 16}px` }}
                          >
                            <div className="font-bold mb-1">{formatHour(event.startHour)} - {formatHour(event.endHour)}</div>
                            <div className="text-clickup-text font-medium">{event.title}</div>
                            <div className="text-gray-500 mt-1 flex items-center gap-1">
                              <MessageSquare size={10} />
                              <span>3 participants</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
        
        <SchedulePopover 
          isOpen={popoverState.isOpen}
          onClose={() => setPopoverState(prev => ({ ...prev, isOpen: false }))}
          position={popoverState.position}
          initialDate={popoverState.initialDate}
          initialStartTime={popoverState.initialStartTime}
          initialEndTime={popoverState.initialEndTime}
        />
      </div>
    </motion.div>
  );
};
