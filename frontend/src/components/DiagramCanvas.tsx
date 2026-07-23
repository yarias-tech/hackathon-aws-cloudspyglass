import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  ReactFlow,
  ReactFlowProvider,
  Background,
  Controls,
  useReactFlow,
  type Node,
  type Edge,
  type NodeTypes,
  type EdgeTypes,
  type FitViewOptions,
  useNodesState,
  useEdgesState,
} from '@xyflow/react';
import dagre from 'dagre';
import '@xyflow/react/dist/style.css';

import type { DiagramData, DiagramNode, DiagramEdge } from '../types/diagram';
import type { ContainerMetadata } from '../types/hierarchy';
import { EmptyState } from './EmptyState';
import { ResourceNode } from './ResourceNode';
import { ContainerNode } from './ContainerNode';
import { BoundaryServiceNode } from './BoundaryServiceNode';
import { RelationshipEdge } from './RelationshipEdge';
import { computeHierarchyLayout } from '../layout/HierarchyLayoutEngine';

/** Register custom node types for React Flow */
const nodeTypes: NodeTypes = {
  resource: ResourceNode,
  container: ContainerNode,
  boundary: BoundaryServiceNode,
};

/** Register custom edge types for React Flow */
const edgeTypes: EdgeTypes = {
  relationship: RelationshipEdge,
};

/** Default node dimensions used for dagre layout calculations */
const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

/** Pan/zoom configuration per Requirement 8.1 */
const MIN_ZOOM = 0.1;
const MAX_ZOOM = 5.0;

const FIT_VIEW_OPTIONS: FitViewOptions = {
  padding: 0.2,
};

/**
 * Applies dagre layout algorithm with top-to-bottom rank direction.
 * Returns positioned React Flow nodes and edges.
 */
function applyDagreLayout(
  diagramNodes: DiagramNode[],
  diagramEdges: DiagramEdge[]
): { nodes: Node[]; edges: Edge[] } {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: 'TB', nodesep: 50, ranksep: 80 });

  // Add nodes to the dagre graph
  for (const node of diagramNodes) {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  }

  // Add edges to the dagre graph
  for (const edge of diagramEdges) {
    graph.setEdge(edge.source, edge.target);
  }

  // Run the layout algorithm
  dagre.layout(graph);

  // Convert dagre node positions to React Flow nodes
  const nodes: Node[] = diagramNodes.map((node) => {
    const dagreNode = graph.node(node.id);
    return {
      id: node.id,
      type: 'resource',
      position: {
        x: dagreNode.x - NODE_WIDTH / 2,
        y: dagreNode.y - NODE_HEIGHT / 2,
      },
      data: {
        label: node.name || node.resource_type,
        resourceType: node.resource_type,
        region: node.region,
        isExternal: node.is_external,
        isUnresolved: node.is_unresolved,
        iconUrl: node.icon_url,
      },
    };
  });

  // Convert diagram edges to React Flow edges using custom RelationshipEdge type
  const edges: Edge[] = diagramEdges.map((edge) => {
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'relationship',
      data: {
        category: edge.category,
        derivedFrom: edge.derived_from,
      },
    };
  });

  return { nodes, edges };
}

/**
 * Collects all resource IDs recursively contained within a container (including nested children).
 */
function getDescendantResourceIds(
  containerId: string,
  containerMap: Map<string, ContainerMetadata>
): Set<string> {
  const result = new Set<string>();
  const container = containerMap.get(containerId);
  if (!container) return result;

  for (const resId of container.resources) {
    result.add(resId);
  }
  for (const childId of container.children) {
    const childResources = getDescendantResourceIds(childId, containerMap);
    for (const resId of childResources) {
      result.add(resId);
    }
  }
  return result;
}

/**
 * Reroutes edges when containers are collapsed. If an edge's source or target
 * is a child resource of a collapsed container, the edge endpoint is rerouted
 * to the collapsed container node instead.
 * (Requirement 8.9)
 */
export function rerouteEdgesForCollapsedContainers(
  edges: Edge[],
  collapsedContainers: Set<string>,
  containerMap: Map<string, ContainerMetadata>
): Edge[] {
  if (collapsedContainers.size === 0) return edges;

  // Build mapping: resource ID → collapsed container ID it belongs to
  const resourceToCollapsedContainer = new Map<string, string>();
  for (const containerId of collapsedContainers) {
    const descendantResources = getDescendantResourceIds(containerId, containerMap);
    for (const resId of descendantResources) {
      resourceToCollapsedContainer.set(resId, containerId);
    }
  }

  // Reroute edges: if source/target is inside a collapsed container, point to container
  const reroutedEdges: Edge[] = edges.map((edge) => {
    const newSource = resourceToCollapsedContainer.get(edge.source) ?? edge.source;
    const newTarget = resourceToCollapsedContainer.get(edge.target) ?? edge.target;

    // Skip self-referencing edges after rerouting (both endpoints same collapsed container)
    if (newSource === newTarget && newSource !== edge.source) {
      return null;
    }

    if (newSource !== edge.source || newTarget !== edge.target) {
      return {
        ...edge,
        id: `${edge.id}__rerouted`,
        source: newSource,
        target: newTarget,
      };
    }
    return edge;
  }).filter((e): e is Edge => e !== null);

  // Deduplicate rerouted edges (multiple children in same container → same rerouted edge)
  const seen = new Set<string>();
  return reroutedEdges.filter((edge) => {
    const key = `${edge.source}→${edge.target}→${(edge.data as { category?: string })?.category ?? ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

interface DiagramCanvasProps {
  data: DiagramData | null;
  /** Whether filters are currently active — affects empty state messaging */
  isFiltered?: boolean;
  /** Callback when a node is clicked — receives the node ID (resource ARN) */
  onNodeClick?: (nodeId: string) => void;
}

/**
 * DiagramCanvas wraps @xyflow/react ReactFlow to render the AWS infrastructure diagram.
 * - Uses hierarchical layout when hierarchy data is present (Requirements 1.1, 6.5)
 * - Falls back to dagre layout with top-to-bottom rank direction when hierarchy is null
 * - Supports pan and zoom within 0.1x to 5.0x range, fitView on load (Requirements 8.1, 8.2)
 * - Shows EmptyState when no scan data exists
 * - Hover highlights connected edges and dims unrelated ones (Requirements 8.6, 8.7)
 * - Fit view button resets viewport (Requirement 8.8)
 * - Reroutes edges to collapsed containers (Requirement 8.9)
 */
export function DiagramCanvas({ data, isFiltered = false, onNodeClick }: DiagramCanvasProps) {
  const hasData = data !== null && data.nodes.length > 0;

  // Show empty state if no data or no nodes
  if (!hasData) {
    if (isFiltered) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            padding: '2rem',
            textAlign: 'center',
            color: '#6b7280',
          }}
          role="status"
          aria-label="No resources match filters"
        >
          <h2 style={{ margin: '0 0 0.5rem', fontSize: '1.25rem', color: '#374151' }}>
            No Resources Match Current Filters
          </h2>
          <p style={{ margin: 0, maxWidth: '400px', lineHeight: 1.6 }}>
            Try adjusting or removing your filters to see resources.
          </p>
        </div>
      );
    }
    return <EmptyState />;
  }

  return (
    <ReactFlowProvider>
      <DiagramCanvasInner data={data} isFiltered={isFiltered} onNodeClick={onNodeClick} />
    </ReactFlowProvider>
  );
}

interface DiagramCanvasInnerProps {
  data: DiagramData;
  isFiltered?: boolean;
  onNodeClick?: (nodeId: string) => void;
}

/**
 * Inner component that uses useReactFlow() hook for fitView button.
 * Must be rendered inside a ReactFlowProvider.
 */
function DiagramCanvasInner({ data, onNodeClick }: DiagramCanvasInnerProps) {
  const { fitView } = useReactFlow();

  // Track collapsed container IDs for centralized state management
  const [collapsedContainers, setCollapsedContainers] = useState<Set<string>>(new Set());

  // Store original edges (before rerouting) for reference during hover highlight
  const originalEdgesRef = useRef<Edge[]>([]);

  // Build container map for hierarchy data
  const containerMap = useMemo(() => {
    const map = new Map<string, ContainerMetadata>();
    if (data.hierarchy) {
      for (const container of data.hierarchy.containers) {
        map.set(container.id, container);
      }
    }
    return map;
  }, [data.hierarchy]);

  // Callback for ContainerNode to call when toggling collapse
  const handleToggleCollapse = useCallback((containerId: string) => {
    setCollapsedContainers((prev) => {
      const next = new Set(prev);
      if (next.has(containerId)) {
        next.delete(containerId);
      } else {
        next.add(containerId);
      }
      return next;
    });
  }, []);

  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(() => {
    if (data.hierarchy != null) {
      const result = computeHierarchyLayout(data.hierarchy, data.nodes, data.edges);

      // Inject onToggleCollapse callback and isCollapsed state into container nodes
      const nodesWithCallbacks = result.nodes.map((node) => {
        if (node.type === 'container') {
          return {
            ...node,
            data: {
              ...node.data,
              isCollapsed: collapsedContainers.has(node.id),
              onToggleCollapse: handleToggleCollapse,
            },
          };
        }
        return node;
      });

      return { nodes: nodesWithCallbacks, edges: result.edges };
    }

    // Fall back to dagre layout when hierarchy is null (backward compat)
    return applyDagreLayout(data.nodes, data.edges);
  }, [data, collapsedContainers, handleToggleCollapse]);

  // Apply edge rerouting when containers are collapsed (Requirement 8.9)
  const processedEdges = useMemo(() => {
    return rerouteEdgesForCollapsedContainers(layoutEdges, collapsedContainers, containerMap);
  }, [layoutEdges, collapsedContainers, containerMap]);

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(processedEdges);

  // Sync nodes/edges when layout data changes (e.g. after filter, scan, or collapse)
  useEffect(() => {
    setNodes(layoutNodes);
    setEdges(processedEdges);
    originalEdgesRef.current = processedEdges;
  }, [layoutNodes, processedEdges, setNodes, setEdges]);

  const handleNodeClick = useCallback(
    (_event: unknown, node: Node) => {
      // Emit selection event with resource ARN (Requirement 8.5)
      if (onNodeClick) {
        onNodeClick(node.id);
      }
    },
    [onNodeClick]
  );

  /**
   * On hover over a resource node: highlight connected edges (3px stroke)
   * and dim unrelated edges to 20% opacity. (Requirement 8.6)
   */
  const handleNodeMouseEnter = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      // Only apply highlight behavior for resource nodes
      if (node.type !== 'resource') return;

      const hoveredNodeId = node.id;

      setEdges((currentEdges) =>
        currentEdges.map((edge) => {
          const isConnected =
            edge.source === hoveredNodeId || edge.target === hoveredNodeId;

          if (isConnected) {
            return {
              ...edge,
              style: {
                ...edge.style,
                strokeWidth: 3,
                opacity: 1,
              },
            };
          }
          return {
            ...edge,
            style: {
              ...edge.style,
              opacity: 0.2,
            },
          };
        })
      );
    },
    [setEdges]
  );

  /**
   * On mouse leave from a resource node: restore all edges to default
   * stroke and opacity. (Requirement 8.7)
   */
  const handleNodeMouseLeave = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      if (node.type !== 'resource') return;

      // Restore original edges (reset stroke width and opacity)
      setEdges((currentEdges) =>
        currentEdges.map((edge) => {
          // Find the original edge to restore its style
          const originalEdge = originalEdgesRef.current.find((e) => e.id === edge.id);
          const originalStyle = originalEdge?.style ?? {};

          return {
            ...edge,
            style: {
              ...originalStyle,
              strokeWidth: 2,
              opacity: 1,
            },
          };
        })
      );
    },
    [setEdges]
  );

  /**
   * "Fit View" button handler — resets viewport to show entire diagram.
   * (Requirement 8.8)
   */
  const handleFitView = useCallback(() => {
    fitView(FIT_VIEW_OPTIONS);
  }, [fitView]);

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onNodeMouseEnter={handleNodeMouseEnter}
        onNodeMouseLeave={handleNodeMouseLeave}
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
      </ReactFlow>
      {/* Dedicated "Fit View" button (Requirement 8.8) */}
      <button
        onClick={handleFitView}
        aria-label="Fit view"
        data-testid="fit-view-button"
        style={{
          position: 'absolute',
          top: 10,
          right: 10,
          zIndex: 10,
          padding: '8px 12px',
          borderRadius: '6px',
          border: '1px solid #d1d5db',
          background: '#ffffff',
          cursor: 'pointer',
          fontSize: '13px',
          fontWeight: 500,
          color: '#374151',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
        }}
      >
        ⊡ Fit View
      </button>
    </div>
  );
}
