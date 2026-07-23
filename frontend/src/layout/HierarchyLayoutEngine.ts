import type { Node, Edge } from '@xyflow/react';
import type {
  HierarchyTree,
  ContainerMetadata,
  BoundaryServicePlacement,
  ContainerType,
} from '../types/hierarchy';
import type { DiagramNode, DiagramEdge } from '../types/diagram';

// ─── Public Interfaces ────────────────────────────────────────────────────────

export interface LayoutOptions {
  containerPadding: number;      // 20px min
  resourceSpacing: number;       // 16px min
  boundaryServiceGap: number;    // 20px min between adjacent boundary services
  minContainerWidth: number;     // 100px
  minContainerHeight: number;    // 60px
}

export interface LayoutResult {
  nodes: Node[];                 // Positioned React Flow nodes (containers + resources)
  edges: Edge[];                 // Styled React Flow edges
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_OPTIONS: LayoutOptions = {
  containerPadding: 20,
  resourceSpacing: 16,
  boundaryServiceGap: 20,
  minContainerWidth: 100,
  minContainerHeight: 60,
};

/** Node dimensions for resource nodes (matches DiagramCanvas constants) */
const NODE_WIDTH = 180;
const NODE_HEIGHT = 60;

/** Boundary service node dimensions */
const BOUNDARY_NODE_WIDTH = 120;
const BOUNDARY_NODE_HEIGHT = 60;

/** Container header height (icon badge 32px + label + vertical padding) */
const CONTAINER_HEADER_HEIGHT = 40;

/** Gap between external resources area and AWS Cloud container */
const EXTERNAL_AREA_GAP = 40;

// ─── Container Styling ────────────────────────────────────────────────────────

interface ContainerStyle {
  border: string;
  background: string;
  borderStyle: string;
}

const CONTAINER_STYLES: Record<string, ContainerStyle> = {
  cloud: {
    border: '2px solid #232F3E',
    background: 'rgba(240, 240, 240, 0.5)',
    borderStyle: 'dashed',
  },
  account: {
    border: '2px solid #DF3312',
    background: 'transparent',
    borderStyle: 'dashed',
  },
  region: {
    border: '2px solid #147EB4',
    background: 'rgba(20, 126, 180, 0.05)',
    borderStyle: 'dashed',
  },
  vpc: {
    border: '2px solid #1B660F',
    background: 'rgba(27, 102, 15, 0.05)',
    borderStyle: 'solid',
  },
  az: {
    border: '1px solid #5A6B7B',
    background: 'transparent',
    borderStyle: 'dashed',
  },
  'subnet-public': {
    border: '2px solid #1B660F',
    background: 'rgba(27, 102, 15, 0.15)',
    borderStyle: 'solid',
  },
  'subnet-private': {
    border: '2px solid #147EB4',
    background: 'rgba(20, 126, 180, 0.15)',
    borderStyle: 'solid',
  },
};

// ─── Edge Styling ─────────────────────────────────────────────────────────────

interface EdgeStyle {
  color: string;
  strokeDasharray?: string;
}

const EDGE_STYLES: Record<string, EdgeStyle> = {
  network: { color: '#2563EB' },
  iam: { color: '#DC2626', strokeDasharray: '5,5' },
  event: { color: '#EA580C', strokeDasharray: '2,2' },
  data: { color: '#7C3AED' },
};

const DEFAULT_EDGE_STYLE: EdgeStyle = { color: '#6B7280' };

// ─── Internal Types ───────────────────────────────────────────────────────────

/** Computed size for a container after recursive layout */
interface ComputedSize {
  width: number;
  height: number;
}

/** Internal layout data accumulated during recursive traversal */
interface ContainerLayoutInfo {
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
}

// ─── Main Layout Function ─────────────────────────────────────────────────────

/**
 * Computes hierarchical layout for React Flow based on an AWS architecture
 * hierarchy tree. Recursively sizes containers from leaves up, positions
 * resource nodes in a grid/flow layout within their containers, places
 * boundary services on container edges, and positions external resources
 * to the right of the AWS Cloud container.
 */
export function computeHierarchyLayout(
  hierarchy: HierarchyTree,
  diagramNodes: DiagramNode[],
  diagramEdges: DiagramEdge[],
  options?: Partial<LayoutOptions>
): LayoutResult {
  const opts: LayoutOptions = { ...DEFAULT_OPTIONS, ...options };

  // Build lookup maps
  const containerMap = new Map<string, ContainerMetadata>();
  for (const container of hierarchy.containers) {
    containerMap.set(container.id, container);
  }

  const diagramNodeMap = new Map<string, DiagramNode>();
  for (const node of diagramNodes) {
    diagramNodeMap.set(node.id, node);
  }

  // Identify external resources (not assigned to any container)
  const assignedResources = new Set<string>();
  for (const container of hierarchy.containers) {
    for (const resId of container.resources) {
      assignedResources.add(resId);
    }
  }

  const externalNodes = diagramNodes.filter(
    (n) => n.is_external || !assignedResources.has(n.id)
  );
  const externalNodeIds = new Set(externalNodes.map((n) => n.id));

  // Boundary service resource IDs (they are positioned separately)
  const boundaryResourceIds = new Set(
    hierarchy.boundary_services.map((bs) => bs.resource_arn)
  );

  // ─── Phase 1: Recursive size computation (bottom-up) ───────────────────────

  const containerSizes = new Map<string, ComputedSize>();

  function computeContainerSize(containerId: string): ComputedSize {
    const cached = containerSizes.get(containerId);
    if (cached) return cached;

    const container = containerMap.get(containerId);
    if (!container) {
      const size = { width: opts.minContainerWidth, height: opts.minContainerHeight };
      containerSizes.set(containerId, size);
      return size;
    }

    // Get resource nodes in this container (exclude boundary services)
    const resourceIds = container.resources.filter(
      (r) => !boundaryResourceIds.has(r) && !externalNodeIds.has(r)
    );

    // Get child containers
    const childContainerIds = container.children;

    // Compute children sizes first (recursive)
    const childSizes: { id: string; size: ComputedSize }[] = [];
    for (const childId of childContainerIds) {
      const childSize = computeContainerSize(childId);
      childSizes.push({ id: childId, size: childSize });
    }

    // Calculate content area needed
    const padding = opts.containerPadding;
    const spacing = opts.resourceSpacing;

    // Layout resources in a grid (flow layout)
    const resourceLayout = computeGridLayout(
      resourceIds.length,
      NODE_WIDTH,
      NODE_HEIGHT,
      spacing
    );

    // Layout child containers horizontally (flow)
    const childrenLayout = computeChildrenFlowLayout(childSizes, spacing);

    // Total content width is the max of resource grid and children flow
    const contentWidth = Math.max(
      resourceLayout.width,
      childrenLayout.width,
      0
    );

    // Total content height stacks: resources on top, children below
    let contentHeight = 0;
    if (resourceLayout.height > 0) {
      contentHeight += resourceLayout.height;
    }
    if (childrenLayout.height > 0) {
      if (contentHeight > 0) contentHeight += spacing;
      contentHeight += childrenLayout.height;
    }

    // Add padding on all sides + header height
    const totalWidth = Math.max(
      contentWidth + padding * 2,
      opts.minContainerWidth
    );
    const totalHeight = Math.max(
      contentHeight + padding * 2 + CONTAINER_HEADER_HEIGHT,
      opts.minContainerHeight
    );

    const size = { width: totalWidth, height: totalHeight };
    containerSizes.set(containerId, size);
    return size;
  }

  // Compute sizes starting from root
  computeContainerSize(hierarchy.root_id);

  // ─── Phase 2: Position assignment (top-down) ───────────────────────────────

  const resultNodes: Node[] = [];
  const containerLayoutInfos = new Map<string, ContainerLayoutInfo>();

  function positionContainer(
    containerId: string,
    parentId: string | null,
    offsetX: number,
    offsetY: number
  ): void {
    const container = containerMap.get(containerId);
    if (!container) return;

    const size = containerSizes.get(containerId)!;
    const containerStyle = getContainerStyle(container.type, container.subnet_type);

    // Create the container node (position is relative to parent in React Flow)
    const containerNode: Node = {
      id: containerId,
      type: 'container',
      position: { x: offsetX, y: offsetY },
      data: {
        label: container.name,
        containerType: container.type,
        subnetType: container.subnet_type,
        iconUrl: container.icon_key,
        isCollapsed: false,
        resourceCount: countRecursiveResources(container, containerMap),
      },
      style: {
        width: size.width,
        height: size.height,
        border: containerStyle.border,
        borderStyle: containerStyle.borderStyle,
        background: containerStyle.background,
        borderRadius: '8px',
        padding: '0',
      },
      ...(parentId ? { parentId } : {}),
    };

    resultNodes.push(containerNode);
    containerLayoutInfos.set(containerId, {
      id: containerId,
      x: offsetX,
      y: offsetY,
      width: size.width,
      height: size.height,
    });

    const padding = opts.containerPadding;
    const spacing = opts.resourceSpacing;

    // Content area starts after header and padding
    let cursorY = CONTAINER_HEADER_HEIGHT + padding;
    const contentStartX = padding;

    // Position resource nodes (grid/flow within container)
    const resourceIds = container.resources.filter(
      (r) => !boundaryResourceIds.has(r) && !externalNodeIds.has(r)
    );

    if (resourceIds.length > 0) {
      const positions = getGridPositions(
        resourceIds.length,
        NODE_WIDTH,
        NODE_HEIGHT,
        spacing,
        size.width - padding * 2
      );

      for (let i = 0; i < resourceIds.length; i++) {
        const resId = resourceIds[i];
        const diagramNode = diagramNodeMap.get(resId);
        const pos = positions[i];

        const resourceNode: Node = {
          id: resId,
          type: 'resource',
          position: {
            x: contentStartX + pos.x,
            y: cursorY + pos.y,
          },
          parentId: containerId,
          data: {
            label: diagramNode?.name || resId,
            resourceType: diagramNode?.resource_type || 'unknown',
            region: diagramNode?.region || '',
            isExternal: false,
            isUnresolved: diagramNode?.is_unresolved || false,
            iconUrl: diagramNode?.icon_url || '',
          },
        };

        resultNodes.push(resourceNode);
      }

      const resourceLayout = computeGridLayout(
        resourceIds.length,
        NODE_WIDTH,
        NODE_HEIGHT,
        spacing
      );
      cursorY += resourceLayout.height + spacing;
    }

    // Position child containers (flow layout)
    const childContainerIds = container.children;
    if (childContainerIds.length > 0) {
      const childSizes = childContainerIds.map((id) => ({
        id,
        size: containerSizes.get(id)!,
      }));

      // Flow layout: place children horizontally, wrapping if needed
      const availableWidth = size.width - padding * 2;
      let childX = contentStartX;
      let childY = cursorY;
      let rowHeight = 0;

      for (const child of childSizes) {
        // Wrap to next row if exceeds available width
        if (
          childX + child.size.width > contentStartX + availableWidth &&
          childX > contentStartX
        ) {
          childX = contentStartX;
          childY += rowHeight + spacing;
          rowHeight = 0;
        }

        positionContainer(child.id, containerId, childX, childY);

        childX += child.size.width + spacing;
        rowHeight = Math.max(rowHeight, child.size.height);
      }
    }
  }

  // Position the root container at origin
  positionContainer(hierarchy.root_id, null, 0, 0);

  // ─── Phase 3: Position boundary services on container edges ────────────────

  // Group boundary services by container edge
  const edgeGroups = new Map<string, BoundaryServicePlacement[]>();
  for (const bs of hierarchy.boundary_services) {
    const key = `${bs.inner_container_id}:${bs.edge_position}`;
    const group = edgeGroups.get(key) || [];
    group.push(bs);
    edgeGroups.set(key, group);
  }

  for (const [, group] of edgeGroups) {
    positionBoundaryGroup(
      group,
      containerSizes,
      containerLayoutInfos,
      containerMap,
      diagramNodeMap,
      resultNodes,
      opts
    );
  }

  // ─── Phase 4: Position external resources ──────────────────────────────────

  const rootSize = containerSizes.get(hierarchy.root_id);
  if (externalNodes.length > 0 && rootSize) {
    const externalStartX = rootSize.width + EXTERNAL_AREA_GAP;
    const externalStartY = 0;

    // Place external resources in a vertical list
    for (let i = 0; i < externalNodes.length; i++) {
      const extNode = externalNodes[i];
      const extFlowNode: Node = {
        id: extNode.id,
        type: 'resource',
        position: {
          x: externalStartX,
          y: externalStartY + i * (NODE_HEIGHT + opts.resourceSpacing),
        },
        data: {
          label: extNode.name || extNode.resource_type,
          resourceType: extNode.resource_type,
          region: extNode.region,
          isExternal: true,
          isUnresolved: extNode.is_unresolved,
          iconUrl: extNode.icon_url,
        },
      };
      resultNodes.push(extFlowNode);
    }
  }

  // ─── Phase 5: Create styled edges ─────────────────────────────────────────

  const resultEdges: Edge[] = diagramEdges.map((edge) => {
    const style = EDGE_STYLES[edge.category] || DEFAULT_EDGE_STYLE;
    const flowEdge: Edge = {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      type: 'relationship',
      data: {
        category: edge.category,
        derivedFrom: edge.derived_from,
        label: edge.label,
      },
      style: {
        stroke: style.color,
        strokeWidth: 2,
        ...(style.strokeDasharray
          ? { strokeDasharray: style.strokeDasharray }
          : {}),
      },
    };
    return flowEdge;
  });

  return { nodes: resultNodes, edges: resultEdges };
}

// ─── Helper Functions ─────────────────────────────────────────────────────────

/**
 * Computes the bounding box of a grid layout for N items.
 */
function computeGridLayout(
  itemCount: number,
  itemWidth: number,
  itemHeight: number,
  spacing: number
): { width: number; height: number } {
  if (itemCount === 0) return { width: 0, height: 0 };

  // Determine columns: aim for a roughly square grid
  const cols = Math.ceil(Math.sqrt(itemCount));
  const rows = Math.ceil(itemCount / cols);

  const width = cols * itemWidth + (cols - 1) * spacing;
  const height = rows * itemHeight + (rows - 1) * spacing;

  return { width, height };
}

/**
 * Computes positions for N items in a grid/flow layout within available width.
 */
function getGridPositions(
  itemCount: number,
  itemWidth: number,
  itemHeight: number,
  spacing: number,
  availableWidth: number
): { x: number; y: number }[] {
  if (itemCount === 0) return [];

  const cols = Math.max(1, Math.floor((availableWidth + spacing) / (itemWidth + spacing)));
  const positions: { x: number; y: number }[] = [];

  for (let i = 0; i < itemCount; i++) {
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions.push({
      x: col * (itemWidth + spacing),
      y: row * (itemHeight + spacing),
    });
  }

  return positions;
}

/**
 * Computes the total bounding box for a horizontal flow of child containers.
 */
function computeChildrenFlowLayout(
  children: { id: string; size: ComputedSize }[],
  spacing: number
): { width: number; height: number } {
  if (children.length === 0) return { width: 0, height: 0 };

  let totalWidth = 0;
  let maxHeight = 0;

  for (let i = 0; i < children.length; i++) {
    totalWidth += children[i].size.width;
    if (i < children.length - 1) totalWidth += spacing;
    maxHeight = Math.max(maxHeight, children[i].size.height);
  }

  return { width: totalWidth, height: maxHeight };
}

/**
 * Positions a group of boundary services on the same container edge.
 * Boundary nodes are positioned with 50% inside and 50% outside the container.
 */
function positionBoundaryGroup(
  group: BoundaryServicePlacement[],
  containerSizes: Map<string, ComputedSize>,
  containerLayoutInfos: Map<string, ContainerLayoutInfo>,
  containerMap: Map<string, ContainerMetadata>,
  diagramNodeMap: Map<string, DiagramNode>,
  resultNodes: Node[],
  opts: LayoutOptions
): void {
  if (group.length === 0) return;

  const containerId = group[0].inner_container_id;
  const edgePosition = group[0].edge_position;
  const containerSize = containerSizes.get(containerId);
  const containerInfo = containerLayoutInfos.get(containerId);

  if (!containerSize || !containerInfo) return;

  // Determine the parent of this container for positioning context
  const container = containerMap.get(containerId);
  const parentId = container?.parent_id || null;

  // Calculate total width/height needed for all boundary nodes on this edge
  const totalNodesWidth =
    group.length * BOUNDARY_NODE_WIDTH +
    (group.length - 1) * opts.boundaryServiceGap;

  // Position boundary nodes centered on the edge
  for (let i = 0; i < group.length; i++) {
    const bs = group[i];
    const diagramNode = diagramNodeMap.get(bs.resource_arn);

    let nodeX: number;
    let nodeY: number;

    // Calculate position based on which edge they're placed on
    // All positions are relative to the container's parent
    switch (edgePosition) {
      case 'top': {
        // Centered horizontally on the top edge
        const startX =
          containerInfo.x +
          (containerSize.width - totalNodesWidth) / 2 +
          i * (BOUNDARY_NODE_WIDTH + opts.boundaryServiceGap);
        nodeX = startX;
        // 50% inside, 50% outside: center on the border
        nodeY = containerInfo.y - BOUNDARY_NODE_HEIGHT / 2;
        break;
      }
      case 'bottom': {
        const startX =
          containerInfo.x +
          (containerSize.width - totalNodesWidth) / 2 +
          i * (BOUNDARY_NODE_WIDTH + opts.boundaryServiceGap);
        nodeX = startX;
        nodeY = containerInfo.y + containerSize.height - BOUNDARY_NODE_HEIGHT / 2;
        break;
      }
      case 'left': {
        nodeX = containerInfo.x - BOUNDARY_NODE_WIDTH / 2;
        const startY =
          containerInfo.y +
          (containerSize.height - totalNodesWidth) / 2 +
          i * (BOUNDARY_NODE_HEIGHT + opts.boundaryServiceGap);
        nodeY = startY;
        break;
      }
      case 'right': {
        nodeX = containerInfo.x + containerSize.width - BOUNDARY_NODE_WIDTH / 2;
        const startY =
          containerInfo.y +
          (containerSize.height - totalNodesWidth) / 2 +
          i * (BOUNDARY_NODE_HEIGHT + opts.boundaryServiceGap);
        nodeY = startY;
        break;
      }
      default: {
        nodeX = containerInfo.x;
        nodeY = containerInfo.y;
      }
    }

    const boundaryNode: Node = {
      id: bs.resource_arn,
      type: 'boundary',
      position: { x: nodeX, y: nodeY },
      ...(parentId ? { parentId } : {}),
      data: {
        label: diagramNode?.name || bs.resource_arn,
        resourceType: diagramNode?.resource_type || bs.boundary_type,
        iconUrl: diagramNode?.icon_url || '',
        boundaryType: bs.boundary_type,
        edgePosition: bs.edge_position,
        innerContainerId: bs.inner_container_id,
      },
    };

    resultNodes.push(boundaryNode);
  }
}

/**
 * Gets the appropriate container style based on type and subnet_type.
 */
function getContainerStyle(
  containerType: ContainerType,
  subnetType: string | null
): ContainerStyle {
  if (containerType === 'subnet' && subnetType) {
    return (
      CONTAINER_STYLES[`subnet-${subnetType}`] ||
      CONTAINER_STYLES['subnet-private']
    );
  }
  return CONTAINER_STYLES[containerType] || CONTAINER_STYLES['vpc'];
}

/**
 * Recursively counts all resources within a container and its descendants.
 */
function countRecursiveResources(
  container: ContainerMetadata,
  containerMap: Map<string, ContainerMetadata>
): number {
  let count = container.resources.length;
  for (const childId of container.children) {
    const child = containerMap.get(childId);
    if (child) {
      count += countRecursiveResources(child, containerMap);
    }
  }
  return count;
}
