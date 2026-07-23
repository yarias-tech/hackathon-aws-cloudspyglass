import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import {
  ExternalResourcesContainer,
  type ExternalResourcesContainerData,
} from './ExternalResourcesContainer';
import type { DiagramNode } from '../types/diagram';

/** Helper to create a mock DiagramNode */
function makeDiagramNode(overrides: Partial<DiagramNode> = {}): DiagramNode {
  return {
    id: 'ext-1',
    resource_type: 'external_service',
    name: 'External Service',
    region: '',
    is_external: true,
    is_unresolved: false,
    icon_url: '',
    ...overrides,
  };
}

/** Wrapper to provide React Flow context required by Handle components */
function renderWithFlow(ui: React.ReactElement) {
  return render(<ReactFlowProvider>{ui}</ReactFlowProvider>);
}

/** Create minimal NodeProps-compatible props for the component */
function makeNodeProps(data: ExternalResourcesContainerData) {
  return {
    id: 'external-container',
    data: data as Record<string, unknown>,
    type: 'externalResources',
    dragging: false,
    isConnectable: true,
    positionAbsoluteX: 0,
    positionAbsoluteY: 0,
    zIndex: 0,
    selected: false,
    deletable: false,
    selectable: true,
    draggable: true,
    parentId: undefined,
    sourcePosition: undefined,
    targetPosition: undefined,
    width: 400,
    height: 300,
  } as any;
}

describe('ExternalResourcesContainer', () => {
  it('renders the container with title', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    expect(
      screen.getByTestId('external-resources-container')
    ).toBeInTheDocument();
    expect(screen.getByText('External Resources')).toBeInTheDocument();
  });

  it('renders default title when label is empty', () => {
    const props = makeNodeProps({
      label: '',
      groups: [],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    expect(screen.getByText('External Resources')).toBeInTheDocument();
  });

  it('renders sub-groups by category with friendly labels', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [
        {
          category: 'cross_account',
          resources: [makeDiagramNode({ id: 'ca-1', name: 'Cross Account RDS' })],
        },
        {
          category: 'on_premises',
          resources: [makeDiagramNode({ id: 'op-1', name: 'On-Prem DB' })],
        },
        {
          category: 'third_party',
          resources: [makeDiagramNode({ id: 'tp-1', name: 'Stripe API' })],
        },
        {
          category: 'unknown',
          resources: [makeDiagramNode({ id: 'uk-1', name: 'Mystery Service' })],
        },
      ],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    expect(screen.getByTestId('external-group-cross_account')).toBeInTheDocument();
    expect(screen.getByTestId('external-group-on_premises')).toBeInTheDocument();
    expect(screen.getByTestId('external-group-third_party')).toBeInTheDocument();
    expect(screen.getByTestId('external-group-unknown')).toBeInTheDocument();

    expect(screen.getByText('Cross-Account AWS')).toBeInTheDocument();
    expect(screen.getByText('On-Premises')).toBeInTheDocument();
    expect(screen.getByText('Third-Party')).toBeInTheDocument();
    expect(screen.getByText('Unknown External')).toBeInTheDocument();
  });

  it('does not render empty groups', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [
        {
          category: 'cross_account',
          resources: [makeDiagramNode({ id: 'ca-1', name: 'Cross Account RDS' })],
        },
        {
          category: 'on_premises',
          resources: [], // empty group should be filtered out
        },
      ],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    expect(screen.getByTestId('external-group-cross_account')).toBeInTheDocument();
    expect(screen.queryByTestId('external-group-on_premises')).not.toBeInTheDocument();
  });

  it('renders external resource nodes with correct data-testid', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [
        {
          category: 'third_party',
          resources: [
            makeDiagramNode({ id: 'tp-1', name: 'Stripe API' }),
            makeDiagramNode({ id: 'tp-2', name: 'Twilio' }),
          ],
        },
      ],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    const nodes = screen.getAllByTestId('external-resource-node');
    expect(nodes).toHaveLength(2);
  });

  it('renders placeholder icon when icon_url is empty', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [
        {
          category: 'unknown',
          resources: [
            makeDiagramNode({ id: 'uk-1', name: 'Unknown', icon_url: '' }),
          ],
        },
      ],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    expect(screen.getByText('?')).toBeInTheDocument();
  });

  it('renders resource name as label', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [
        {
          category: 'cross_account',
          resources: [
            makeDiagramNode({ id: 'ca-1', name: 'Remote DynamoDB' }),
          ],
        },
      ],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    expect(screen.getByText('Remote DynamoDB')).toBeInTheDocument();
  });

  it('applies dashed border styling via CSS class on resource nodes', () => {
    const props = makeNodeProps({
      label: 'External Resources',
      groups: [
        {
          category: 'unknown',
          resources: [makeDiagramNode({ id: 'uk-1', name: 'Test Node' })],
        },
      ],
    });

    renderWithFlow(<ExternalResourcesContainer {...props} />);

    const node = screen.getByTestId('external-resource-node');
    expect(node).toHaveClass('external-resources-container__resource-node');
  });
});
