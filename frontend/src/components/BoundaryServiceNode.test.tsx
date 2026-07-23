import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { BoundaryServiceNode, type BoundaryServiceNodeData } from './BoundaryServiceNode';

/** Wrapper to provide React Flow context required by Handle components */
function renderWithFlow(ui: React.ReactElement) {
  return render(<ReactFlowProvider>{ui}</ReactFlowProvider>);
}

/** Create minimal NodeProps-compatible props for BoundaryServiceNode */
function makeNodeProps(data: Partial<BoundaryServiceNodeData> = {}) {
  const defaultData: BoundaryServiceNodeData = {
    label: 'Internet Gateway',
    resourceType: 'aws_internet_gateway',
    iconUrl: '/icons/igw.svg',
    boundaryType: 'igw',
  };
  return {
    id: 'boundary-1',
    data: { ...defaultData, ...data } as Record<string, unknown>,
    type: 'boundaryService',
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
    width: 80,
    height: 80,
  } as any;
}

describe('BoundaryServiceNode', () => {
  describe('icon rendering', () => {
    it('renders img element when iconUrl is provided', () => {
      const props = makeNodeProps({ iconUrl: '/icons/igw.svg' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const img = screen.getByRole('img');
      expect(img).toHaveAttribute('src', '/icons/igw.svg');
    });

    it('renders placeholder icon when iconUrl is empty', () => {
      const props = makeNodeProps({ iconUrl: '' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      expect(screen.getByText('?')).toBeInTheDocument();
      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });

    it('shows placeholder icon on img load error', () => {
      const props = makeNodeProps({ iconUrl: '/icons/broken.svg' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const img = screen.getByRole('img');
      fireEvent.error(img);

      expect(screen.getByText('?')).toBeInTheDocument();
      expect(screen.queryByRole('img')).not.toBeInTheDocument();
    });

    it('alt text on icon image contains the boundary type', () => {
      const props = makeNodeProps({ boundaryType: 'nat', iconUrl: '/icons/nat.svg' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const img = screen.getByRole('img');
      expect(img).toHaveAttribute('alt', 'nat service icon');
    });
  });

  describe('label rendering', () => {
    it('renders the label text correctly', () => {
      const props = makeNodeProps({ label: 'NAT Gateway' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      expect(screen.getByText('NAT Gateway')).toBeInTheDocument();
    });
  });

  describe('boundary type styling', () => {
    it('applies boundary-service-node--igw class for igw type', () => {
      const props = makeNodeProps({ boundaryType: 'igw' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const node = screen.getByTestId('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node--igw');
    });

    it('applies boundary-service-node--nat class for nat type', () => {
      const props = makeNodeProps({ boundaryType: 'nat' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const node = screen.getByTestId('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node--nat');
    });

    it('applies boundary-service-node--waf class for waf type', () => {
      const props = makeNodeProps({ boundaryType: 'waf' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const node = screen.getByTestId('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node--waf');
    });

    it('applies boundary-service-node--vpn class for vpn type', () => {
      const props = makeNodeProps({ boundaryType: 'vpn' });
      renderWithFlow(<BoundaryServiceNode {...props} />);

      const node = screen.getByTestId('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node');
      expect(node).toHaveClass('boundary-service-node--vpn');
    });
  });
});
