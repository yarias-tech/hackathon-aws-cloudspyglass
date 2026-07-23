import { useCallback, useEffect, useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
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
import { EmptyState } from './EmptyState';
import { ResourceNode } from './ResourceNode';
import { RelationshipEdge } from './RelationshipEdge';

/** Register custom node types for React Flow */
const nodeTypes: NodeTypes = {
  resource: ResourceNode,
};

/** Register custom edge types for React Flow */
const edgeTypes: EdgeTypes = {
  relationship: RelationshipEdge,
};

/** Default node dimensions used for dagre layout calculations */
const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

/** Pan/zoom configuration per Requirement 5.5 */
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 4.0;

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

interface DiagramCanvasProps {
  data: DiagramData | null;
  /** Whether filters are currently active — affects empty state messaging */
  isFiltered?: boolean;
  /** Callback when a node is clicked — receives the node ID (resource ARN) */
  onNodeClick?: (nodeId: string) => void;
}

/**
 * DiagramCanvas wraps @xyflow/react ReactFlow to render the AWS infrastructure diagram.
 * - Applies dagre layout with top-to-bottom rank direction (Requirement 5.4)
 * - Supports pan and zoom within 0.25x to 4.0x range, fitView on load (Requirement 5.5)
 * - Shows EmptyState when no scan data exists (Requirement 5.7)
 */
export function DiagramCanvas({ data, isFiltered = false, onNodeClick }: DiagramCanvasProps) {
  const hasData = data !== null && data.nodes.length > 0;

  const { nodes: layoutNodes, edges: layoutEdges } = useMemo(
    () =>
      hasData
        ? applyDagreLayout(data.nodes, data.edges)
        : { nodes: [], edges: [] },
    [data, hasData]
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layoutEdges);

  // Sync nodes/edges when layout data changes (e.g. after filter or scan)
  useEffect(() => {
    setNodes(layoutNodes);
    setEdges(layoutEdges);
  }, [layoutNodes, layoutEdges, setNodes, setEdges]);

  const onInit = useCallback(() => {
    // fitView is handled declaratively via the fitView prop
  }, []);

  const handleNodeClick = useCallback((_event: unknown, node: Node) => {
    if (onNodeClick) {
      onNodeClick(node.id);
    }
  }, [onNodeClick]);

  // Show empty state if no data or no nodes
  if (!hasData) {
    if (isFiltered) {
      // Filters are active but produced no results
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
    <div style={{ width: '100%', height: '100%' }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        onInit={onInit}
        fitView
        fitViewOptions={FIT_VIEW_OPTIONS}
        minZoom={MIN_ZOOM}
        maxZoom={MAX_ZOOM}
        attributionPosition="bottom-left"
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}
