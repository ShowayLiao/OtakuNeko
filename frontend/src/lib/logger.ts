type LogLevel = 'debug' | 'info' | 'warn' | 'error';

interface LogContext {
  componentName?: string;
  operation?: string;
  [key: string]: unknown;
}

interface LogEntry {
  level: LogLevel;
  timestamp: string;
  context: LogContext;
  message: string;
  data?: unknown;
}

const LOG_LEVELS: Record<LogLevel, number> = {
  debug: 0,
  info: 1,
  warn: 2,
  error: 3,
};

const CURRENT_LOG_LEVEL: LogLevel = process.env.NODE_ENV === 'production' ? 'error' : 'debug';

function shouldLog(level: LogLevel): boolean {
  return LOG_LEVELS[level] >= LOG_LEVELS[CURRENT_LOG_LEVEL];
}

function formatLogEntry(entry: LogEntry): string {
  const { level, timestamp, context, message, data } = entry;
  const contextStr = Object.keys(context).length > 0 ? ` | Context: ${JSON.stringify(context)}` : '';
  const dataStr = data !== undefined ? ` | Data: ${JSON.stringify(data)}` : '';
  return `[${timestamp}] [${level.toUpperCase()}]${contextStr} | ${message}${dataStr}`;
}

function createLogEntry(level: LogLevel, message: string, context: LogContext, data?: unknown): LogEntry {
  return {
    level,
    timestamp: new Date().toISOString(),
    context,
    message,
    data,
  };
}

function log(level: LogLevel, message: string, context: LogContext = {}, data?: unknown): void {
  if (!shouldLog(level)) {
    return;
  }

  const entry = createLogEntry(level, message, context, data);
  const formattedLog = formatLogEntry(entry);

  switch (level) {
    case 'debug':
      console.debug(formattedLog);
      break;
    case 'info':
      console.info(formattedLog);
      break;
    case 'warn':
      console.warn(formattedLog);
      break;
    case 'error':
      console.error(formattedLog);
      break;
  }
}

export const logger = {
  debug: (message: string, context?: LogContext, data?: unknown) => log('debug', message, context, data),
  info: (message: string, context?: LogContext, data?: unknown) => log('info', message, context, data),
  warn: (message: string, context?: LogContext, data?: unknown) => log('warn', message, context, data),
  error: (message: string, context?: LogContext, data?: unknown) => log('error', message, context, data),
};

export const createComponentLogger = (componentName: string) => ({
  debug: (operation: string, message: string, data?: unknown) => 
    logger.debug(message, { componentName, operation }, data),
  info: (operation: string, message: string, data?: unknown) => 
    logger.info(message, { componentName, operation }, data),
  warn: (operation: string, message: string, data?: unknown) => 
    logger.warn(message, { componentName, operation }, data),
  error: (operation: string, message: string, data?: unknown) => 
    logger.error(message, { componentName, operation }, data),
});

export type { LogContext, LogEntry, LogLevel };
