import { http, HttpResponse } from 'msw';
import type { DiagramData } from '../../types/diagram';
import type { CredentialStatus } from '../../types/credentials';
import type { AppSettings } from '../../types/settings';
import type { FilteredResult, TagSuggestion } from '../../types/filters';

/**
 * Mock data for integration tests
 */
export const mockDiagramData: DiagramData = {
  nodes: [
    {
      id: 'ec2-1',
      resource_type: 'ec2',
      name: 'web-server-1',
      region: 'us-east-1',
      is_external: false,
      is_unresolved: false,
      icon_url: '/api/images/icons/ec2',
    },
    {
      id: 'rds-1',
      resource_type: 'rds',
      name: 'main-database',
      region: 'us-east-1',
      is_external: false,
      is_unresolved: false,
      icon_url: '/api/images/icons/rds',
    },
    {
      id: 'lambda-1',
      resource_type: 'lambda',
      name: 'api-handler',
      region: 'us-east-1',
      is_external: false,
      is_unresolved: false,
      icon_url: '/api/images/icons/lambda',
    },
  ],
  edges: [
    {
      id: 'edge-1',
      source: 'ec2-1',
      target: 'rds-1',
      category: 'network',
      derived_from: 'security_group',
      label: null,
    },
    {
      id: 'edge-2',
      source: 'lambda-1',
      target: 'rds-1',
      category: 'data',
      derived_from: 'vpc_config',
      label: null,
    },
  ],
  account_id: '123456789012',
  scan_timestamp: '2024-01-15T10:30:00Z',
  total_resources: 3,
  scanned_regions: ['us-east-1'],
  failures: [],
};

export const mockDisconnectedStatus: CredentialStatus = {
  connected: false,
  account_id: null,
  credential_source: null,
  expiry: null,
  status: 'Disconnected',
};

export const mockConnectedStatus: CredentialStatus = {
  connected: true,
  account_id: '123456789012',
  credential_source: 'ui',
  expiry: '2024-01-15T22:00:00Z',
  status: 'Connected',
};

export const mockSettings: AppSettings = {
  auto_refresh_interval: 'manual',
  selected_regions: ['us-east-1', 'us-west-2'],
};

export const mockFilteredResult: FilteredResult = {
  diagram: {
    nodes: [mockDiagramData.nodes[0]], // only ec2
    edges: [],
    account_id: '123456789012',
    scan_timestamp: '2024-01-15T10:30:00Z',
    total_resources: 3,
    scanned_regions: ['us-east-1'],
    failures: [],
  },
  filtered_count: 1,
  total_count: 3,
  active_filters: {
    tag_filters: [],
    type_filters: ['ec2'],
  },
};

export const mockTagSuggestions: TagSuggestion[] = [
  { key: 'env', value: 'production', count: 5 },
  { key: 'env', value: 'staging', count: 3 },
  { key: 'team', value: 'backend', count: 2 },
];

/**
 * Default MSW request handlers for all API endpoints
 */
export const handlers = [
  // Credential status
  http.get('/api/credentials/status', () => {
    return HttpResponse.json(mockDisconnectedStatus);
  }),

  // Credential submission
  http.post('/api/credentials', () => {
    return HttpResponse.json(mockConnectedStatus);
  }),

  // Credential deletion
  http.delete('/api/credentials', () => {
    return HttpResponse.json(mockDisconnectedStatus);
  }),

  // Settings
  http.get('/api/settings', () => {
    return HttpResponse.json(mockSettings);
  }),

  http.put('/api/settings', () => {
    return HttpResponse.json(mockSettings);
  }),

  // Scan
  http.post('/api/scan', () => {
    return HttpResponse.json({ status: 'completed' });
  }),

  http.get('/api/scan/status', () => {
    return HttpResponse.json({ status: 'completed', progress: 100 });
  }),

  // Diagrams
  http.get('/api/diagrams/latest', () => {
    return HttpResponse.json(mockDiagramData);
  }),

  // Filtered diagrams
  http.get('/api/diagrams/latest/filtered', () => {
    return HttpResponse.json(mockFilteredResult);
  }),

  // Tag suggestions
  http.get('/api/tags/suggestions', () => {
    return HttpResponse.json(mockTagSuggestions);
  }),

  // Images (icons) - return empty SVG
  http.get('/api/images/icons/:serviceType', () => {
    return new HttpResponse('<svg></svg>', {
      headers: { 'Content-Type': 'image/svg+xml' },
    });
  }),

  // Logo
  http.get('/api/images/logo', () => {
    return new HttpResponse('<svg></svg>', {
      headers: { 'Content-Type': 'image/svg+xml' },
    });
  }),
];
