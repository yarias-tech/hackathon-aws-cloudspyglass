import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { DetailPanel } from './DetailPanel';
import type { Resource } from '../types/resources';
import type { ErrorResponse } from '../types/errors';

const mockResource: Resource = {
  arn: 'arn:aws:ec2:us-east-1:123456789012:instance/i-abc123',
  resource_type: 'ec2',
  name: 'web-server-01',
  region: 'us-east-1',
  tags: { Environment: 'production', Team: 'platform' },
  creation_date: '2024-01-15T10:30:00Z',
  iam_role: 'arn:aws:iam::123456789012:role/EC2Role',
  attributes: { instance_type: 'm5.large', state: 'running' },
  is_external: false,
  is_unresolved: false,
};

const mockError: ErrorResponse = {
  error_code: 'RESOURCE_NOT_FOUND',
  message: 'The requested resource could not be found',
  details: null,
  timestamp: '2024-01-15T10:30:00Z',
  recoverable: false,
};

describe('DetailPanel', () => {
  describe('Rendering — not visible when closed', () => {
    it('renders nothing when resource is null and not loading', () => {
      const { container } = render(
        <DetailPanel resource={null} onClose={vi.fn()} />
      );
      expect(container.querySelector('.detail-panel')).not.toBeInTheDocument();
    });
  });

  describe('Metadata display (Requirement 6.1)', () => {
    it('displays resource type in header', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(screen.getByText('ec2')).toBeInTheDocument();
    });

    it('displays ARN', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(
        screen.getByText('arn:aws:ec2:us-east-1:123456789012:instance/i-abc123')
      ).toBeInTheDocument();
    });

    it('displays region', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(screen.getByText('us-east-1')).toBeInTheDocument();
    });

    it('displays tags as key-value pairs', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(screen.getByText('Environment')).toBeInTheDocument();
      expect(screen.getByText('production')).toBeInTheDocument();
      expect(screen.getByText('Team')).toBeInTheDocument();
      expect(screen.getByText('platform')).toBeInTheDocument();
    });

    it('displays creation date', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(screen.getByText('2024-01-15T10:30:00Z')).toBeInTheDocument();
    });

    it('displays IAM role', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(
        screen.getByText('arn:aws:iam::123456789012:role/EC2Role')
      ).toBeInTheDocument();
    });

    it('displays service-specific attributes', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(screen.getByText('m5.large')).toBeInTheDocument();
      expect(screen.getByText('running')).toBeInTheDocument();
    });
  });

  describe('Omit non-applicable sections (Requirement 6.1)', () => {
    it('omits tags section when tags are empty', () => {
      const resource: Resource = { ...mockResource, tags: {} };
      render(<DetailPanel resource={resource} onClose={vi.fn()} />);
      expect(screen.queryByText('Tags')).not.toBeInTheDocument();
    });

    it('omits IAM role section when null', () => {
      const resource: Resource = { ...mockResource, iam_role: null };
      render(<DetailPanel resource={resource} onClose={vi.fn()} />);
      expect(screen.queryByText('IAM Role')).not.toBeInTheDocument();
    });

    it('omits creation date section when null', () => {
      const resource: Resource = { ...mockResource, creation_date: null };
      render(<DetailPanel resource={resource} onClose={vi.fn()} />);
      expect(screen.queryByText('Creation Date')).not.toBeInTheDocument();
    });

    it('omits attributes section when empty', () => {
      const resource: Resource = { ...mockResource, attributes: {} };
      render(<DetailPanel resource={resource} onClose={vi.fn()} />);
      expect(screen.queryByText('Attributes')).not.toBeInTheDocument();
    });
  });

  describe('Loading state (Requirement 6.2)', () => {
    it('shows loading indicator when loading', () => {
      render(
        <DetailPanel resource={null} loading={true} onClose={vi.fn()} />
      );
      expect(screen.getByText('Loading resource details…')).toBeInTheDocument();
    });

    it('renders the panel during loading', () => {
      const { container } = render(
        <DetailPanel resource={null} loading={true} onClose={vi.fn()} />
      );
      expect(container.querySelector('.detail-panel')).toBeInTheDocument();
    });
  });

  describe('Error state (Requirement 6.3)', () => {
    it('displays error message', () => {
      render(
        <DetailPanel resource={null} error={mockError} onClose={vi.fn()} />
      );
      expect(
        screen.getByText('The requested resource could not be found')
      ).toBeInTheDocument();
    });

    it('displays error code', () => {
      render(
        <DetailPanel resource={null} error={mockError} onClose={vi.fn()} />
      );
      expect(screen.getByText('RESOURCE_NOT_FOUND')).toBeInTheDocument();
    });

    it('renders the panel during error state', () => {
      const { container } = render(
        <DetailPanel resource={null} error={mockError} onClose={vi.fn()} />
      );
      expect(container.querySelector('.detail-panel')).toBeInTheDocument();
    });
  });

  describe('Close behavior (Requirement 6.4)', () => {
    it('calls onClose when close button is clicked', () => {
      const onClose = vi.fn();
      render(<DetailPanel resource={mockResource} onClose={onClose} />);
      fireEvent.click(screen.getByLabelText('Close detail panel'));
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('calls onClose when Escape key is pressed', () => {
      const onClose = vi.fn();
      render(<DetailPanel resource={mockResource} onClose={onClose} />);
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(onClose).toHaveBeenCalledTimes(1);
    });

    it('does not call onClose for non-Escape keys', () => {
      const onClose = vi.fn();
      render(<DetailPanel resource={mockResource} onClose={onClose} />);
      fireEvent.keyDown(document, { key: 'Enter' });
      expect(onClose).not.toHaveBeenCalled();
    });
  });

  describe('Content replacement (Requirement 6.5)', () => {
    it('replaces content when resource changes', () => {
      const { rerender } = render(
        <DetailPanel resource={mockResource} onClose={vi.fn()} />
      );
      expect(screen.getByText('web-server-01')).toBeInTheDocument();

      const newResource: Resource = {
        ...mockResource,
        arn: 'arn:aws:lambda:us-west-2:123456789012:function:my-func',
        resource_type: 'lambda',
        name: 'my-func',
        region: 'us-west-2',
      };
      rerender(<DetailPanel resource={newResource} onClose={vi.fn()} />);
      expect(screen.getByText('my-func')).toBeInTheDocument();
      expect(screen.queryByText('web-server-01')).not.toBeInTheDocument();
    });
  });

  describe('Accessibility', () => {
    it('has complementary role for landmark navigation', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(screen.getByRole('complementary')).toBeInTheDocument();
    });

    it('has aria-label on the panel', () => {
      render(<DetailPanel resource={mockResource} onClose={vi.fn()} />);
      expect(
        screen.getByLabelText('Resource detail panel')
      ).toBeInTheDocument();
    });
  });
});
