import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  ChevronLeft, 
  ChevronRight, 
  Plus, 
  MessageSquare 
} from 'lucide-react';
import { cn } from '@/src/lib/utils';
import { getKoreanHolidayNames } from '@/src/lib/korean-holidays';
import { SchedulePopover } from './SchedulePopover';

const MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTH_NAMES_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PICKER_DAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

interface DatePickerPopoverProps {
  pickerYear: number;
  pickerMonth: number;
  viewYear: number;
  viewMonth: number;
  selectedDate: number;
  today: Date;
  onPrev: () => void;
  onNext: () => void;
  onPickToday: () => void;
  onPickDate: (year: number, month: number, day: number) => void;
}

function DatePickerPopover({
  pickerYear,
  pickerMonth,
  viewYear,
  viewMonth,
  selectedDate,
  today,
  onPrev,
  onNext,
  onPickToday,
  onPickDate,
}: DatePickerPopoverProps) {
  // 6×7 grid: leading blanks for the days before the 1st, then days, then
  // trailing blanks. We always render 42 cells so the popover height never
  // jumps as the user browses across months.
  const leadingBlanks = new Date(pickerYear, pickerMonth, 1).getDay();
  const daysInMonth = new Date(pickerYear, pickerMonth + 1, 0).getDate();
  const cells = Array.from({ length: 42 }, (_, i) => {
    const dayNumber = i - leadingBlanks + 1;
    return dayNumber >= 1 && dayNumber <= daysInMonth ? dayNumber : 0;
  });

  return (
    <div
      role="dialog"
      aria-label="Choose a date"
      className="absolute right-0 top-full mt-2 z-40 w-72 rounded-lg border border-app-border bg-app-surface p-3 shadow-xl"
    >
      <div className="flex items-center justify-between mb-2">
        <button
          type="button"
          onClick={onPrev}
          aria-label="Previous month"
          className="flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
        >
          <ChevronLeft size={14} />
        </button>
        <div className="app-text-control text-app-ink tabular-nums">
          {MONTH_NAMES_LONG[pickerMonth]} {pickerYear}
        </div>
        <button
          type="button"
          onClick={onNext}
          aria-label="Next month"
          className="flex h-7 w-7 items-center justify-center rounded text-gray-500 hover:bg-app-surface-hover hover:text-app-ink"
        >
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="grid grid-cols-7 mb-1">
        {PICKER_DAYS.map((day, i) => (
          <div
            key={i}
            className={cn(
              'app-text-overline py-1 text-center',
              i === 0 ? 'text-red-500' : 'text-gray-500',
            )}
          >
            {day}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-7 gap-0.5">
        {cells.map((day, i) => {
          if (day === 0) {
            return <div key={i} className="h-8" />;
          }
          const isToday =
            pickerYear === today.getFullYear() &&
            pickerMonth === today.getMonth() &&
            day === today.getDate();
          const isSelected =
            pickerYear === viewYear &&
            pickerMonth === viewMonth &&
            day === selectedDate;
          const cellDate = new Date(pickerYear, pickerMonth, day);
          const isSunday = cellDate.getDay() === 0;
          const holidayNames = getKoreanHolidayNames(pickerYear, pickerMonth, day);
          return (
            <button
              type="button"
              key={i}
              onClick={() => onPickDate(pickerYear, pickerMonth, day)}
              title={holidayNames ? holidayNames.join(', ') : undefined}
              className={cn(
                'app-text-control-sm flex h-8 items-center justify-center rounded transition-colors tabular-nums',
                isSelected
                  ? 'bg-app-accent text-app-bg font-semibold'
                  : isToday
                    ? 'border border-app-accent text-app-accent font-semibold hover:bg-app-surface-hover'
                    : holidayNames || isSunday
                      ? 'text-red-500 hover:bg-app-surface-hover'
                      : 'text-app-ink hover:bg-app-surface-hover',
              )}
            >
              {day}
            </button>
          );
        })}
      </div>

      <div className="mt-2 flex justify-between border-t border-app-border pt-2">
        <button
          type="button"
          onClick={onPickToday}
          className="app-text-control-sm rounded px-2 py-1 text-app-accent hover:bg-app-surface-hover"
        >
          Today
        </button>
      </div>
    </div>
  );
}

export const PlannerView = () => {
  const today = new Date();
  const [viewMode, setViewMode] = useState<'Month' | 'Week' | 'Day'>('Month');
  const [selectedDate, setSelectedDate] = useState(today.getDate());
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());
  const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

  // Build a 5-row month grid containing the active month, with leading/trailing
  // padding from the surrounding months represented as <= 0 or > daysInMonth.
  const dates = (() => {
    const firstOfMonth = new Date(viewYear, viewMonth, 1);
    const leadingBlanks = firstOfMonth.getDay();
    const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
    return Array.from({ length: 35 }, (_, i) => i - leadingBlanks + 1).map((d) => (
      d >= 1 && d <= daysInMonth ? d : 0
    ));
  })();

  // Week containing the currently selected date.
  const weekDates = (() => {
    const anchor = new Date(viewYear, viewMonth, selectedDate);
    const sundayOffset = anchor.getDay();
    return Array.from({ length: 7 }, (_, i) => {
      const d = new Date(anchor);
      d.setDate(anchor.getDate() - sundayOffset + i);
      return d.getDate();
    });
  })();

  const events: { date: number; title: string; color: string; startHour: number; endHour: number }[] = [];

  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ date: number, hour: number } | null>(null);
  const [dragEnd, setDragEnd] = useState<{ date: number, hour: number } | null>(null);
  const [popoverState, setPopoverState] = useState<{
    isOpen: boolean;
    initialDate?: string;
    initialStartTime?: string;
    initialEndTime?: string;
  }>({ isOpen: false });

  const containerRef = useRef<HTMLDivElement>(null);

  // Mini date-picker popover. The picker has its own (year, month) cursor so
  // the user can browse without committing — the main view only updates when
  // they actually click a day.
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerYear, setPickerYear] = useState(today.getFullYear());
  const [pickerMonth, setPickerMonth] = useState(today.getMonth());
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!pickerOpen) return;
    function onMouseDown(event: MouseEvent) {
      if (pickerRef.current && !pickerRef.current.contains(event.target as Node)) {
        setPickerOpen(false);
      }
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setPickerOpen(false);
    }
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [pickerOpen]);

  // When the popover opens, sync its cursor to whatever the main view is showing.
  const openPicker = () => {
    setPickerYear(viewYear);
    setPickerMonth(viewMonth);
    setPickerOpen(true);
  };

  useEffect(() => {
    const handleGlobalMouseUp = () => {
      if (isDragging) {
        setIsDragging(false);
      }
    };
    window.addEventListener('mouseup', handleGlobalMouseUp);
    return () => window.removeEventListener('mouseup', handleGlobalMouseUp);
  }, [isDragging]);

  // Allow the SubSidebar header "+" button to open the schedule popover
  // without owning a reference to this component.
  useEffect(() => {
    const handler = () => setPopoverState({ isOpen: true });
    window.addEventListener('planner:create-event', handler);
    return () => window.removeEventListener('planner:create-event', handler);
  }, []);

  const handleDateClick = (_e: React.MouseEvent, date: number) => {
    if (date > 0) {
      if (viewMode === 'Month') {
        setSelectedDate(date);
        setPopoverState({
          isOpen: true,
          initialDate: `${MONTH_NAMES[viewMonth]} ${date}, ${viewYear}`,
          initialStartTime: '09:00 AM',
          initialEndTime: '10:00 AM',
        });
      } else {
        setSelectedDate(date);
        setViewMode('Day');
      }
    }
  };

  const formatHour = (h: number) => {
    if (h === 0) return '12:00 AM';
    if (h === 12) return '12:00 PM';
    return h > 12 ? `${h - 12}:00 PM` : `${h}:00 AM`;
  };

  const formatHourShort = (h: number) => {
    if (h === 0) return '12 AM';
    if (h === 12) return '12 PM';
    return h > 12 ? `${h - 12} PM` : `${h} AM`;
  };

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

  const goToPreviousMonth = () => {
    const next = new Date(viewYear, viewMonth - 1, 1);
    setViewYear(next.getFullYear());
    setViewMonth(next.getMonth());
  };

  const goToNextMonth = () => {
    const next = new Date(viewYear, viewMonth + 1, 1);
    setViewYear(next.getFullYear());
    setViewMonth(next.getMonth());
  };

  const goToToday = () => {
    const now = new Date();
    setViewYear(now.getFullYear());
    setViewMonth(now.getMonth());
    setSelectedDate(now.getDate());
  };

  const handleMouseUp = (_e: React.MouseEvent) => {
    if (isDragging && dragStart && dragEnd) {
      setIsDragging(false);

      const startHour = Math.min(dragStart.hour, dragEnd.hour);
      const endHour = Math.max(dragStart.hour, dragEnd.hour) + 1;

      setPopoverState({
        isOpen: true,
        initialDate: `${MONTH_NAMES[viewMonth]} ${dragStart.date}, ${viewYear}`,
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
          <h1 className="app-text-title-lg text-app-ink">Planner</h1>
          <div className="flex items-center bg-app-surface-sidebar border border-app-border rounded-md p-1">
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
                    ? "bg-app-surface-hover text-app-ink shadow-sm" 
                    : "text-gray-500 hover:text-app-ink"
                )}
              >
                {mode}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={goToToday}
            className="app-text-control-sm rounded-md border border-app-border px-3 py-1 text-gray-500 transition-colors hover:text-app-ink"
          >
            Today
          </button>
        </div>
        <div className="flex items-center gap-3">
          <div ref={pickerRef} className="relative flex items-center gap-1">
            <button
              type="button"
              onClick={goToPreviousMonth}
              aria-label="Previous month"
              className="flex h-8 w-8 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => (pickerOpen ? setPickerOpen(false) : openPicker())}
              aria-haspopup="dialog"
              aria-expanded={pickerOpen}
              className="app-text-control flex h-8 min-w-[180px] items-center justify-center rounded-md text-app-ink tabular-nums transition-colors hover:bg-app-surface-hover"
            >
              {viewMode === 'Day'
                ? `${MONTH_NAMES_LONG[viewMonth]} ${selectedDate}, ${viewYear}`
                : `${MONTH_NAMES_LONG[viewMonth]} ${viewYear}`}
            </button>
            <button
              type="button"
              onClick={goToNextMonth}
              aria-label="Next month"
              className="flex h-8 w-8 items-center justify-center rounded-md text-gray-500 transition-colors hover:bg-app-surface-hover hover:text-app-ink"
            >
              <ChevronRight size={16} />
            </button>
            {pickerOpen ? (
              <DatePickerPopover
                pickerYear={pickerYear}
                pickerMonth={pickerMonth}
                viewYear={viewYear}
                viewMonth={viewMonth}
                selectedDate={selectedDate}
                today={today}
                onPrev={() => {
                  const next = new Date(pickerYear, pickerMonth - 1, 1);
                  setPickerYear(next.getFullYear());
                  setPickerMonth(next.getMonth());
                }}
                onNext={() => {
                  const next = new Date(pickerYear, pickerMonth + 1, 1);
                  setPickerYear(next.getFullYear());
                  setPickerMonth(next.getMonth());
                }}
                onPickToday={() => {
                  goToToday();
                  setPickerOpen(false);
                }}
                onPickDate={(year, month, day) => {
                  setViewYear(year);
                  setViewMonth(month);
                  setSelectedDate(day);
                  setPickerOpen(false);
                }}
              />
            ) : null}
          </div>
          <button className="app-text-control flex items-center gap-2 rounded-md bg-app-accent px-4 py-2 text-app-bg">
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
              <div className="grid grid-cols-7 border-b border-app-border">
                {days.map(day => (
                  <div key={day} className="app-text-overline border-r border-app-border py-2 text-center text-gray-500 last:border-r-0">
                    {day}
                  </div>
                ))}
              </div>
              <div className="flex-1 grid grid-cols-7 grid-rows-5">
                {dates.map((date, i) => {
                  const isToday = date > 0
                    && viewYear === today.getFullYear()
                    && viewMonth === today.getMonth()
                    && date === today.getDate();
                  const cellDate = new Date(viewYear, viewMonth, date);
                  const isSunday = date > 0 && cellDate.getDay() === 0;
                  const holidayNames = date > 0
                    ? getKoreanHolidayNames(viewYear, viewMonth, date)
                    : null;
                  return (
                  <div
                    key={i}
                    onClick={(e) => handleDateClick(e, date)}
                    className={cn(
                      "p-2 border-r border-b border-app-border last:border-r-0 min-h-[100px] hover:bg-app-surface-hover transition-colors cursor-pointer group",
                      date === 0 && "bg-app-surface-sidebar/50 cursor-default hover:bg-app-surface-sidebar/50"
                    )}
                  >
                    <div className={cn(
                      "app-text-control-sm mb-2",
                      isToday
                        ? "w-6 h-6 bg-app-accent text-app-bg rounded-full flex items-center justify-center -mt-1 -ml-1"
                        : holidayNames || isSunday
                          ? "text-red-500 font-medium"
                          : "text-gray-500"
                    )}>
                      {date > 0 ? date : ''}
                    </div>
                    {holidayNames ? (
                      <div className="app-text-micro mb-1 truncate text-red-500" title={holidayNames.join(', ')}>
                        {holidayNames[0]}
                      </div>
                    ) : null}
                    
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
                  );
                })}
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
              <div className="flex border-b border-app-border">
                <div className="w-16 shrink-0"></div>
                <div className="flex-1 grid grid-cols-7">
                  {days.map((day, i) => {
                    const isToday = weekDates[i] === today.getDate()
                      && viewMonth === today.getMonth()
                      && viewYear === today.getFullYear();
                    const isHoliday = !!getKoreanHolidayNames(viewYear, viewMonth, weekDates[i]);
                    const isSunday = i === 0;
                    return (
                    <div
                      key={day}
                      onClick={() => {
                        setSelectedDate(weekDates[i]);
                        setViewMode('Day');
                      }}
                      className="py-3 text-center border-r border-app-border last:border-r-0 hover:bg-app-surface-hover cursor-pointer transition-colors"
                    >
                      <div className={cn(
                        "app-text-overline mb-1",
                        isHoliday || isSunday ? "text-red-500" : "text-gray-500"
                      )}>{day}</div>
                      <div className={cn(
                        "app-text-title-md font-bold",
                        isToday
                          ? "text-app-accent"
                          : isHoliday || isSunday
                            ? "text-red-500"
                            : "text-app-ink"
                      )}>
                        {weekDates[i]}
                      </div>
                    </div>
                    );
                  })}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto custom-scrollbar relative">
                {Array.from({ length: 24 }, (_, i) => i).map(hour => (
                  <div key={hour} className="flex">
                    <div className="app-text-overline relative -top-3 w-16 shrink-0 py-2 pr-4 text-right text-gray-600">
                      {formatHourShort(hour)}
                    </div>
                    <div className="flex-1 grid grid-cols-7">
                      {weekDates.map(date => (
                        <div 
                          key={`${date}-${hour}`}
                          className="border-t border-r border-app-border last:border-r-0 h-12 relative group"
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
              <div className="p-6 border-b border-app-border flex items-center gap-6">
                <div className="w-16 h-16 bg-app-accent rounded-xl flex flex-col items-center justify-center text-app-accent-fg shadow-sm">
                  <span className="app-text-overline">{MONTH_NAMES[viewMonth]}</span>
                  <span className="app-text-title-lg font-black">{selectedDate}</span>
                </div>
                <div>
                  <h2 className="app-text-title-lg text-app-ink">
                    {(() => {
                      const dayLabels = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
                      return dayLabels[new Date(viewYear, viewMonth, selectedDate).getDay()];
                    })()}
                  </h2>
                  {(() => {
                    const holidayNames = getKoreanHolidayNames(viewYear, viewMonth, selectedDate);
                    if (holidayNames) {
                      return (
                        <p className="app-text-body text-red-500 font-medium">
                          {holidayNames.join(' · ')}
                        </p>
                      );
                    }
                    return (
                      <p className="app-text-body text-gray-500">
                        You have {events.filter(e => e.date === selectedDate).length} event(s) scheduled for today.
                      </p>
                    );
                  })()}
                </div>
              </div>

              <div className="flex-1 overflow-y-auto custom-scrollbar p-6">
                <div className="max-w-4xl mx-auto">
                  {Array.from({ length: 24 }, (_, i) => i).map(hour => (
                    <div key={hour} className="flex group">
                      <div className="app-text-label relative -top-3 w-20 shrink-0 py-2 pr-6 text-right text-gray-600">
                        {formatHourShort(hour)}
                      </div>
                      <div 
                        className="flex-1 border-t border-app-border h-16 relative"
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
                            <div className="text-app-ink font-medium">{event.title}</div>
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
          initialDate={popoverState.initialDate}
          initialStartTime={popoverState.initialStartTime}
          initialEndTime={popoverState.initialEndTime}
        />
      </div>
    </motion.div>
  );
};
