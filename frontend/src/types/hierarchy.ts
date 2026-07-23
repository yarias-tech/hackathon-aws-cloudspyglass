export type ContainerType = 'cloud' | 'account' | 'region' | 'vpc' | 'az' | 'subnet';
export type SubnetType = 'public' | 'private';
export type BoundaryType = 'igw' | 'nat' | 'waf' | 'vpn';
export type EdgePosition = 'top' | 'bottom' | 'left' | 'right';

export interface ContainerMetadata {
  id: string;
  name: string;
  type: ContainerType;
  parent_id: string | null;
  subnet_type: SubnetType | null;
  icon_key: string;
  resources: string[];
  children: string[];
}

export interface BoundaryServicePlacement {
  resource_arn: string;
  boundary_type: BoundaryType;
  inner_container_id: string;
  outer_container_id: string | null;
  edge_position: EdgePosition;
}

export interface HierarchyTree {
  containers: ContainerMetadata[];
  root_id: string;
  boundary_services: BoundaryServicePlacement[];
}
