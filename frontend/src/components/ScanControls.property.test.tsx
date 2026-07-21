import { render, screen, act, cleanup } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import * as fc from 'fast-check';
import { ScanControls } from './ScanControls';
import type { DiagramData } from '../types/diagram';

// Mock the apiClient module
vi.mock('../api/apiClient', () => {
  const ApiError = class extends Error {
    statusCode: number;
    errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean };
    constructor(statusCode: number, errorResponse: { error_code: string; message: string; details: null; timestamp: string; recoverable: boolean }) {
      super(errorResponse.message);
      this.name = 'ApiError';
      this.statusCode = statusCode;
      this.errorResponse = errorResponse;
    }
    get recoverable() { return this.errorResponse.recoverable; }
    get errorCode() { return this.errorResponse.error_code; }
  };

  return {
    ApiError,
    apiClient: {
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    },
  };
});

import { apiClient, ApiError } from '../api/apiClient';

// --- Arbitraries ---

/** Arbitrary for DiagramNode */
const diagramNodeArb = fc.record({
  id: fc.uuid(),
  resource_type: fc.constantFrom('ec2', 'lambda', 's3', 'rds', 'vpc', 'iam_role', 'ecs', 'dynamodb'),
  name: fc.string({ minLength: 1, maxLength: 50 }),
  region: fc.constantFrom('us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'),
  is_external: fc.boolean(),
  is_unresolved: fc.boolean(),
  icon_url: fc.constant('/api/images/icons/ec2'),
});

/** Arbitrary for DiagramEdge */
const diagramEdgeArb = fc.record({
  id: fc.uuid(),
  source: fc.uuid(),
  target: fc.uuid(),
  category: fc.constantFrom('network' as const, 'iam' as const, 'event' as const, 'data' as const),
  derived_from: fc.string({ minLength: 1, maxLength: 30 }),
  label: fc.option(fc.string({ minLength: 1, maxLength: 20 }), { nil: null }),
});

/** Arbitrary for RegionFailure */
const regionFailureArb = fc.record({
  region: fc.constantFrom('us-east-1', 'us-west-2', 'eu-west-1'),
  resource_type: fc.constantFrom('ec2', 'lambda', 's3'),
  error_message: fc.string({ minLength: 1, maxLength: 50 }),
  timestamp: fc.constant('2024-01-15T10:30:00Z'),
});

/** Arbitrary for DiagramData (the current state that should be preserved) */
const diagramDataArb: fc.Arbitrary<DiagramData> = fc.record({
  nodes: fc.array(diagramNodeArb, { minLength: 0, maxLength: 5 }),
  edges: fc.array(diagramEdgeArb, { minLength: 0, maxLength: 5 }),
  account_id: fc.stringMatching(/^[0-9]{12}$/),
  scan_timestamp: fc.constant('2024-01-15T10:30:00Z'),
  total_resources: fc.nat({ max: 100 }),
  scanned_regions: fc.subarray(['us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1'], { minLength: 1 }),
  failures: fc.array(regionFailureArb, { minLength: 0, maxLength: 2 }),
});

/** Arbitrary for non-409 error scenarios that should trigger onError */
const errorScenarioArb = fc.record({
  statusCode: fc.constantFrom(400, 401, 403, 404, 500, 502, 503),
  errorCode: fc.constantFrom(
    'INTERNAL_ERROR', 'INVALID_CREDENTIALS', 'SCAN_FAILED',
    'RATE_LIMIT_EXCEEDED', 'SERVICE_UNAVAILABLE', 'UNKNOWN_ERROR'
  ),
  message: fc.string({ minLength: 1, maxLength: 80 }),
  recoverable: fc.boolean(),
});

/** Arbitrary for 409 SCAN_IN_PROGRESS scenario (silent skip) */
const scanInProgressArb = fc.record({
  statusCode: fc.constant(409 as const),
  errorCode: fc.constant('SCAN_IN_PROGRESS'),
  message: fc.string({ minLength: 1, maxLength: 80 }),
  recoverable: fc.constant(true),
});

/**
 * **Validates: Requirements 9.4**
 *
 * Property 20: Diagram state preservation on refresh failure
 * For any valid DiagramData state and any type of scan failure during auto-refresh,
 * the onScanComplete callback is NEVER called (meaning diagram data remains unchanged),
 * and onError IS called with the error message.
 */
describe('Property 20: Diagram state preservation on refresh failure', () => {
  let onScanComplete: ReturnType<typeof vi.fn>;
  let onError: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.useFakeTimers();
    onScanComplete = vi.fn();
    onError = vi.fn();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('failed auto-refresh never calls onScanComplete (diagram state preserved) and calls onError', async () => {
    await fc.assert(
      fc.asyncProperty(
        diagramDataArb,
        errorScenarioArb,
        async (_diagramData, errorScenario) => {
          // Reset mocks for each property run
          vi.clearAllMocks();
          cleanup();

          // Mock apiClient.post to reject with the generated error
          vi.mocked(apiClient.post).mockRejectedValue(
            new ApiError(errorScenario.statusCode, {
              error_code: errorScenario.errorCode,
              message: errorScenario.message,
              details: null,
              timestamp: '2024-01-15T10:30:00Z',
              recoverable: errorScenario.recoverable,
            })
          );

          // Render ScanControls with auto-refresh enabled at 1m
          render(
            <ScanControls
              autoRefreshInterval="1m"
              onScanComplete={onScanComplete}
              onError={onError}
            />
          );

          // Advance timers to trigger the auto-refresh (1 minute)
          await act(async () => {
            await vi.advanceTimersByTimeAsync(60_000);
          });

          // Property: onScanComplete is NEVER called (diagram data preserved)
          expect(onScanComplete).not.toHaveBeenCalled();

          // Property: onError IS called with the error message
          expect(onError).toHaveBeenCalledTimes(1);
          expect(onError).toHaveBeenCalledWith(errorScenario.message);
        }
      ),
      { numRuns: 30 }
    );
  });

  it('409 SCAN_IN_PROGRESS neither calls onScanComplete nor onError (silent skip)', async () => {
    await fc.assert(
      fc.asyncProperty(
        diagramDataArb,
        scanInProgressArb,
        async (_diagramData, errorScenario) => {
          // Reset mocks for each property run
          vi.clearAllMocks();
          cleanup();

          // Mock apiClient.post to reject with 409
          vi.mocked(apiClient.post).mockRejectedValue(
            new ApiError(errorScenario.statusCode, {
              error_code: errorScenario.errorCode,
              message: errorScenario.message,
              details: null,
              timestamp: '2024-01-15T10:30:00Z',
              recoverable: errorScenario.recoverable,
            })
          );

          // Render ScanControls with auto-refresh enabled
          render(
            <ScanControls
              autoRefreshInterval="1m"
              onScanComplete={onScanComplete}
              onError={onError}
            />
          );

          // Advance timers to trigger auto-refresh
          await act(async () => {
            await vi.advanceTimersByTimeAsync(60_000);
          });

          // Property: onScanComplete is NOT called (diagram state preserved)
          expect(onScanComplete).not.toHaveBeenCalled();

          // Property: onError is NOT called (409 is silently skipped)
          expect(onError).not.toHaveBeenCalled();
        }
      ),
      { numRuns: 20 }
    );
  });

  it('non-ApiError failures also preserve diagram state and report generic error', async () => {
    await fc.assert(
      fc.asyncProperty(
        diagramDataArb,
        fc.string({ minLength: 1, maxLength: 50 }),
        async (_diagramData, errorMessage) => {
          // Reset mocks for each property run
          vi.clearAllMocks();
          cleanup();

          // Mock apiClient.post to throw a generic Error (not ApiError)
          vi.mocked(apiClient.post).mockRejectedValue(new Error(errorMessage));

          // Render ScanControls with auto-refresh enabled
          render(
            <ScanControls
              autoRefreshInterval="1m"
              onScanComplete={onScanComplete}
              onError={onError}
            />
          );

          // Advance timers to trigger auto-refresh
          await act(async () => {
            await vi.advanceTimersByTimeAsync(60_000);
          });

          // Property: onScanComplete is NOT called (diagram state preserved)
          expect(onScanComplete).not.toHaveBeenCalled();

          // Property: onError IS called with the generic message
          expect(onError).toHaveBeenCalledTimes(1);
          expect(onError).toHaveBeenCalledWith('Scan failed unexpectedly');
        }
      ),
      { numRuns: 20 }
    );
  });
});
