import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ResourceNode } from './ResourceNode';

// Mock @xyflow/react Handle component
vi.mock('@xyflow/react', () => ({
  Handle: ({ type, position }: { type: string; position: string }) => (
    <div data-testid={`handle-${type}`} data-position={position} />
  ),
  Position: {
    Top: 'top',
    Bottom: 'bottom',
    Left: 'left',
    Right: 'right',
  },
}));

const baseProps = {
  id: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123',
  type: 'resource',
  data: {
    label: 'web-server-01',
    resourceType: 'ec2',
    region: 'us-east-1',
    isExternal: false,
    isUnresolved: false,
    iconUrl: '/api/images/icons/ec2',
  },
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
  width: 180,
  height: 60,
  measured: { width: 180, height: 60 },
};

describe('ResourceNode', () => {
  describe('Basic rendering (Requirement 5.1)', () => {
    it('renders the resource name', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      expect(screen.getByText('web-server-01')).toBeInTheDocument();
    });

    it('renders the resource type', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      expect(screen.getByText('ec2')).toBeInTheDocument();
    });

    it('renders the icon from the icon URL', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      const img = screen.getByAltText('ec2 icon');
      expect(img).toBeInTheDocument();
      expect(img).toHaveAttribute('src', '/api/images/icons/ec2');
    });

    it('renders top and bottom handles for connections', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      expect(screen.getByTestId('handle-target')).toHaveAttribute('data-position', 'top');
      expect(screen.getByTestId('handle-source')).toHaveAttribute('data-position', 'bottom');
    });
  });

  describe('External components (Requirement 5.6)', () => {
    it('applies dashed border class for external components', () => {
      const externalProps = {
        ...baseProps,
        data: { ...baseProps.data, isExternal: true },
      };
      const { container } = render(<ResourceNode {...(externalProps as any)} />);
      const node = container.querySelector('.resource-node');
      expect(node).toHaveClass('resource-node--external');
    });

    it('does not apply dashed border class for internal components', () => {
      const { container } = render(<ResourceNode {...(baseProps as any)} />);
      const node = container.querySelector('.resource-node');
      expect(node).not.toHaveClass('resource-node--external');
    });
  });

  describe('Icon rendering at 48x48 (Requirement 2.2)', () => {
    it('renders icon with width and height of 48', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      const img = screen.getByAltText('ec2 icon');
      expect(img).toHaveAttribute('width', '48');
      expect(img).toHaveAttribute('height', '48');
    });

    it('renders icon inside a centered icon container above the label', () => {
      const { container } = render(<ResourceNode {...(baseProps as any)} />);
      const node = container.querySelector('.resource-node');
      const icon = container.querySelector('.resource-node__icon');
      const info = container.querySelector('.resource-node__info');
      // Icon should appear before info in DOM order (above in vertical layout)
      expect(node?.children[0]).toBe(icon);
      expect(node?.children[1]).toBe(info);
    });
  });

  describe('Placeholder icon when no mapping exists (Requirement 2.3)', () => {
    it('shows placeholder when iconUrl is empty string', () => {
      const noIconProps = {
        ...baseProps,
        data: { ...baseProps.data, iconUrl: '' },
      };
      render(<ResourceNode {...(noIconProps as any)} />);
      const placeholder = screen.getByLabelText('ec2 icon placeholder');
      expect(placeholder).toBeInTheDocument();
      expect(placeholder).toHaveTextContent('?');
    });

    it('shows placeholder when iconUrl is undefined', () => {
      const noIconProps = {
        ...baseProps,
        data: { ...baseProps.data, iconUrl: undefined },
      };
      render(<ResourceNode {...(noIconProps as any)} />);
      const placeholder = screen.getByLabelText('ec2 icon placeholder');
      expect(placeholder).toBeInTheDocument();
      expect(placeholder).toHaveTextContent('?');
    });

    it('placeholder is a 48x48 gray square with "?" symbol', () => {
      const noIconProps = {
        ...baseProps,
        data: { ...baseProps.data, iconUrl: '' },
      };
      const { container } = render(<ResourceNode {...(noIconProps as any)} />);
      const placeholder = container.querySelector('.resource-node__icon--placeholder');
      expect(placeholder).toBeInTheDocument();
      expect(placeholder).toHaveTextContent('?');
    });
  });

  describe('Placeholder icon on load failure (Requirement 2.6)', () => {
    it('shows placeholder icon when image fails to load', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      const img = screen.getByAltText('ec2 icon');
      fireEvent.error(img);
      expect(screen.getByLabelText('ec2 icon placeholder')).toBeInTheDocument();
      expect(screen.queryByAltText('ec2 icon')).not.toBeInTheDocument();
    });

    it('placeholder displays "?" symbol on load failure', () => {
      render(<ResourceNode {...(baseProps as any)} />);
      const img = screen.getByAltText('ec2 icon');
      fireEvent.error(img);
      const placeholder = screen.getByLabelText('ec2 icon placeholder');
      expect(placeholder).toHaveTextContent('?');
    });
  });

  describe('Unresolved resources', () => {
    it('applies unresolved class for unresolved resources', () => {
      const unresolvedProps = {
        ...baseProps,
        data: { ...baseProps.data, isUnresolved: true },
      };
      const { container } = render(<ResourceNode {...(unresolvedProps as any)} />);
      const node = container.querySelector('.resource-node');
      expect(node).toHaveClass('resource-node--unresolved');
    });
  });
});
