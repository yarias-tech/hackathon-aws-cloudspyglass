import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ReactFlowProvider } from '@xyflow/react';
import { ContainerNode, type ContainerNodeData } from './ContainerNode';

/** Wrapper to provide React Flow context required by Handle components */
function renderWithFlow(ui: React.ReactElement) {
  return render(<ReactFlowProvider>{ui}</ReactFlowProvider>);
}

/** Create minimal NodeProps-compatible props for the component */
function makeNodeProps(data: Partial<ContainerNodeData> = {}) {
  const defaultData: ContainerNodeData = {
    label: 'Test Container',
    containerType: 'vpc',
    iconUrl: '',
    isCollapsed: false,
    resourceCount: 0,
  };
  return {
    id: 'container-1',
    data: { ...defaultData, ...data } as Record<string, unknown>,
    type: 'container',
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

describe('ContainerNode', () => {
  describe('container type styling', () => {
    it('applies container-node--cloud class for cloud type', () => {
      const props = makeNodeProps({ containerType: 'cloud' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node');
      expect(node).toHaveClass('container-node--cloud');
    });

    it('applies container-node--account class for account type', () => {
      const props = makeNodeProps({ containerType: 'account' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--account');
    });

    it('applies container-node--region class for region type', () => {
      const props = makeNodeProps({ containerType: 'region' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--region');
    });

    it('applies container-node--vpc class for vpc type', () => {
      const props = makeNodeProps({ containerType: 'vpc' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--vpc');
    });

    it('applies container-node--az class for az type', () => {
      const props = makeNodeProps({ containerType: 'az' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--az');
    });

    it('applies container-node--subnet-public class for public subnet', () => {
      const props = makeNodeProps({ containerType: 'subnet', subnetType: 'public' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--subnet-public');
    });

    it('applies container-node--subnet-private class for private subnet', () => {
      const props = makeNodeProps({ containerType: 'subnet', subnetType: 'private' });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--subnet-private');
    });
  });

  describe('collapsed state', () => {
    it('shows resource count badge when collapsed', () => {
      const props = makeNodeProps({ isCollapsed: true, resourceCount: 5 });
      renderWithFlow(<ContainerNode {...props} />);

      const badge = screen.getByLabelText('resource count');
      expect(badge).toBeInTheDocument();
      expect(badge).toHaveTextContent('5');
    });

    it('does not show resource count badge when expanded', () => {
      const props = makeNodeProps({ isCollapsed: false, resourceCount: 5 });
      renderWithFlow(<ContainerNode {...props} />);

      expect(screen.queryByLabelText('resource count')).not.toBeInTheDocument();
    });

    it('applies collapsed class when collapsed', () => {
      const props = makeNodeProps({ isCollapsed: true });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).toHaveClass('container-node--collapsed');
    });

    it('does not apply collapsed class when expanded', () => {
      const props = makeNodeProps({ isCollapsed: false });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(node).not.toHaveClass('container-node--collapsed');
    });
  });

  describe('double-click toggle', () => {
    it('calls onToggleCollapse with container ID on double-click', () => {
      const onToggleCollapse = vi.fn();
      const props = makeNodeProps({ isCollapsed: false, resourceCount: 3, onToggleCollapse });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      fireEvent.doubleClick(node);

      expect(onToggleCollapse).toHaveBeenCalledWith('container-1');
    });

    it('shows collapsed state when isCollapsed prop is true', () => {
      const props = makeNodeProps({ isCollapsed: true, resourceCount: 7 });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(screen.getByLabelText('resource count')).toBeInTheDocument();
      expect(screen.getByLabelText('resource count')).toHaveTextContent('7');
      expect(node).toHaveClass('container-node--collapsed');
    });

    it('shows expanded state when isCollapsed prop is false', () => {
      const props = makeNodeProps({ isCollapsed: false, resourceCount: 3 });
      renderWithFlow(<ContainerNode {...props} />);

      const node = screen.getByTestId('container-node');
      expect(screen.queryByLabelText('resource count')).not.toBeInTheDocument();
      expect(node).not.toHaveClass('container-node--collapsed');
    });
  });

  describe('label and icon', () => {
    it('renders the label text', () => {
      const props = makeNodeProps({ label: 'us-east-1' });
      renderWithFlow(<ContainerNode {...props} />);

      expect(screen.getByText('us-east-1')).toBeInTheDocument();
    });

    it('renders placeholder icon when iconUrl is empty', () => {
      const props = makeNodeProps({ iconUrl: '' });
      renderWithFlow(<ContainerNode {...props} />);

      expect(screen.getByText('☁')).toBeInTheDocument();
    });

    it('renders img element when iconUrl is provided', () => {
      const props = makeNodeProps({ iconUrl: '/icons/vpc.svg' });
      renderWithFlow(<ContainerNode {...props} />);

      const img = screen.getByRole('img');
      expect(img).toHaveAttribute('src', '/icons/vpc.svg');
    });
  });
});
