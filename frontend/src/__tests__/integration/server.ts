import { setupServer } from 'msw/node';
import { handlers } from './handlers';

/**
 * MSW server instance for integration tests.
 * Uses the default handlers from handlers.ts.
 * Tests can override individual handlers using server.use().
 */
export const server = setupServer(...handlers);
