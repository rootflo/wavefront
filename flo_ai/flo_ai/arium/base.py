import inspect
from functools import partial
from flo_ai.arium.nodes import AriumNode, ForEachNode
from flo_ai.arium.protocols import ExecutableNode
from flo_ai.models.agent import Agent
from flo_ai.tool.base_tool import Tool
from flo_ai.utils.logger import logger
from typing import List, Optional, Callable, Literal, get_origin, get_args, Dict
from flo_ai.arium.models import StartNode, EndNode, Edge, default_router
from pathlib import Path


class BaseArium:
    def __init__(self):
        self.start_node_name = '__start__'
        self.end_node_names: set = set()  # Support multiple end nodes
        self.nodes: Dict[str, ExecutableNode | StartNode | EndNode] = dict[
            str, ExecutableNode | StartNode | EndNode
        ]()
        self.edges: Dict[str, Edge] = dict[str, Edge]()

    def add_nodes(self, agents: List[ExecutableNode | StartNode | EndNode]):
        self.nodes.update({agent.name: agent for agent in agents})

    def start_at(self, node: ExecutableNode):
        start_node = StartNode()
        if start_node.name in self.nodes:
            raise ValueError(f'Start node {start_node.name} already exists')
        self.nodes[start_node.name] = start_node
        self.edges[start_node.name] = Edge(
            router_fn=partial(default_router, to_node=node.name), to_nodes=[node.name]
        )

    def add_end_to(self, node: ExecutableNode):
        # Create a unique end node name for this specific node
        end_node_name = f'__end__{node.name}__'
        end_node = EndNode()
        end_node.name = end_node_name

        # Add this end node name to our set of possible end nodes
        self.end_node_names.add(end_node_name)

        # Only add the end node if it doesn't exist yet
        if end_node_name not in self.nodes:
            self.nodes[end_node_name] = end_node

        self.edges[node.name] = Edge(
            router_fn=partial(default_router, to_node=end_node_name),
            to_nodes=[end_node_name],
        )

    def _check_router_return_type(self, router: Callable) -> Optional[List]:
        try:
            # Get the function signature
            sig = inspect.signature(router)
            return_annotation = sig.return_annotation

            # Check if there's no return annotation
            if return_annotation == inspect.Signature.empty:
                return None

            # Check if the return type is a Literal
            origin = get_origin(return_annotation)

            # In Python 3.8+, Literal types have get_origin() return typing.Literal
            if origin is Literal:
                # Extract the literal values
                literal_values = list(get_args(return_annotation))
                return literal_values

            return None

        except Exception as e:
            logger.error(f'Error checking router return type: {e}')
            return None

    def add_edge(
        self,
        from_node: str,
        to_nodes: List[str] = None,
        router: Optional[Callable] = None,
    ):
        if router and not callable(router):
            raise ValueError('Router must be a callable')

        if not to_nodes:
            raise ValueError('To nodes must be provided')

        if not router and len(to_nodes) != 1:
            raise ValueError(
                'Exactly one to node must be provided if router is not provided'
            )

        if from_node not in self.nodes:
            raise ValueError(f'Node {from_node} not found')

        wrong_nodes = [
            wrong_to_node
            for wrong_to_node in to_nodes
            if wrong_to_node not in self.nodes
        ]
        if wrong_nodes:
            raise ValueError(f'Nodes {wrong_nodes} not found')

        if router:
            literal_values = self._check_router_return_type(router)
            if literal_values is None:
                raise ValueError('Router return type is not a Literal')

            # Check if router supports self-reference
            supports_self_ref = getattr(router, 'supports_self_reference', False)

            # For self-referencing routers, we need to include the from_node in valid targets
            valid_targets = to_nodes.copy()
            if supports_self_ref:
                valid_targets.append(from_node)

            invalid_literals = [
                val for val in literal_values if val not in valid_targets
            ]
            if invalid_literals:
                raise ValueError(
                    f'Router return type includes literal values {invalid_literals} that are not in valid targets {valid_targets}'
                )

            # For self-referencing routers, allow router options to include from_node
            if supports_self_ref:
                # Router can return any of: to_nodes + from_node, but must include all to_nodes
                missing_targets = [
                    node for node in to_nodes if node not in literal_values
                ]
                if missing_targets:
                    raise ValueError(
                        f'Self-referencing router must include all to_nodes {to_nodes}, missing: {missing_targets}'
                    )
            else:
                # Non-self-referencing routers must match exactly
                if set(literal_values) != set(to_nodes):
                    raise ValueError(
                        f'Router return type values {literal_values} do not match to_nodes {to_nodes}'
                    )

        self.edges[from_node] = Edge(
            router_fn=router
            if router
            else partial(default_router, to_node=to_nodes[0]),
            to_nodes=to_nodes,
        )

    def check_orphan_nodes(self) -> List[str]:
        if not self.nodes:
            return []

        # Get all nodes with outgoing edges
        nodes_with_outgoing = set(self.edges.keys())

        # Get all nodes with incoming edges by examining router return types and to_nodes
        nodes_with_incoming = set()

        for _, target in self.edges.items():
            nodes_with_incoming.update(target.to_nodes)

        # Find orphan nodes: nodes that have neither incoming nor outgoing edges
        all_nodes = set(self.nodes.keys())
        connected_nodes = nodes_with_outgoing.union(nodes_with_incoming)
        orphan_nodes = all_nodes - connected_nodes

        return list(orphan_nodes)

    def validate_graph(self) -> bool:
        orphan_nodes = self.check_orphan_nodes()

        if orphan_nodes:
            raise ValueError(
                f'Orphan nodes found: {orphan_nodes}. These nodes have no incoming or outgoing edges.'
            )

        # Check for exactly 1 start node
        start_nodes = [
            node for node in self.nodes.values() if isinstance(node, StartNode)
        ]
        if len(start_nodes) == 0:
            raise ValueError(
                f'Graph must have exactly 1 start node. Found 0 start nodes: {start_nodes}'
            )
        elif len(start_nodes) > 1:
            raise ValueError(
                f'Graph must have exactly 1 start node. Found {len(start_nodes)} start nodes.'
            )

        # Check for at least 1 end node
        end_nodes = [node for node in self.nodes.values() if isinstance(node, EndNode)]
        if len(end_nodes) == 0:
            raise ValueError('Graph must have at least 1 end node. Found 0 end nodes.')

        return True

    def visualize_graph(
        self,
        output_path: str = 'graph_visualization.png',
        graph_title: str = 'Arium Graph Visualization',
        figsize: tuple = (12, 8),
        node_size: int = 3000,
        font_size: int = 10,
        dpi: int = 300,
    ) -> None:
        """
        Generate a graph visualization and save it as PNG.

        Args:
            output_path: Path where the PNG file will be saved
            figsize: Figure size as (width, height) in inches
            node_size: Size of the nodes in the graph
            font_size: Font size for node labels
            dpi: Resolution of the saved image
        """
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        import networkx as nx

        if not self.nodes:
            logger.error('No nodes to visualize')
            return

        # Create directed graph
        G = nx.DiGraph()

        # Add nodes with their types
        for node_name, node in self.nodes.items():
            node_type = self._get_node_type(node)
            G.add_node(node_name, node_type=node_type, node_obj=node)

        # Add edges
        for from_node, edge in self.edges.items():
            for to_node in edge.to_nodes:
                if to_node in self.nodes:
                    G.add_edge(from_node, to_node, edge_obj=edge)

        # Create matplotlib figure
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)

        # Use hierarchical layout for better DAG visualization
        try:
            # Try different layouts for better DAG appearance
            pos = nx.nx_agraph.graphviz_layout(G, prog='dot', args='-Grankdir=TB')
        except Exception as e:
            logger.error(f'Error in graphviz_layout: {e}')
            try:
                # Fallback to planar layout for DAG structure
                pos = nx.planar_layout(G)
            except Exception as e:
                logger.error(f'Error in graphviz_layout: {e}')
                # Final fallback to shell layout for better hierarchy
                pos = nx.shell_layout(G)

        # Define colors for different node types
        node_colors = {
            'start': '#90EE90',  # Light green
            'end': '#FFB6C1',  # Light pink
            'agent': '#87CEEB',  # Sky blue
            'tool': '#DDA0DD',  # Plum
        }

        # Draw nodes with different colors based on type
        for node_name, node_data in G.nodes(data=True):
            node_type = node_data['node_type']
            color = node_colors.get(node_type, '#CCCCCC')

            nx.draw_networkx_nodes(
                G,
                pos,
                nodelist=[node_name],
                node_color=color,
                node_size=node_size,
                alpha=0.9,
                ax=ax,
            )

        # Separate edges by router type for different styling
        default_edges = []
        custom_edges = []

        for edge_data in G.edges(data=True):
            from_node, to_node, data = edge_data
            edge_obj = data['edge_obj']

            if edge_obj.is_default_router():
                default_edges.append((from_node, to_node))
            else:
                custom_edges.append((from_node, to_node))

        # Draw default router edges with dotted lines
        if default_edges:
            nx.draw_networkx_edges(
                G,
                pos,
                edgelist=default_edges,
                edge_color='gray',
                arrows=True,
                arrowsize=20,
                arrowstyle='->',
                connectionstyle='arc3,rad=0.1',
                style='solid',
                width=2,
                ax=ax,
            )

        # Draw custom router edges with solid lines
        if custom_edges:
            nx.draw_networkx_edges(
                G,
                pos,
                edgelist=custom_edges,
                edge_color='black',
                arrows=True,
                arrowsize=20,
                arrowstyle='->',
                connectionstyle='arc3,rad=0.1',
                style='dotted',
                width=2,
                ax=ax,
            )

        # Add labels
        nx.draw_networkx_labels(G, pos, font_size=font_size, font_weight='bold', ax=ax)

        # Add title
        plt.title(graph_title, fontsize=16, fontweight='bold', pad=20)

        # Add legend
        legend_elements = [
            patches.Patch(color='#90EE90', label='Start Node'),
            patches.Patch(color='#FFB6C1', label='End Node'),
            patches.Patch(color='#87CEEB', label='Agent'),
            patches.Patch(color='#DDA0DD', label='Tool'),
            patches.Patch(
                facecolor='none',
                edgecolor='gray',
                linestyle='dotted',
                linewidth=2,
                label='Default Router',
            ),
            patches.Patch(
                facecolor='none',
                edgecolor='black',
                linestyle='solid',
                linewidth=2,
                label='Custom Router',
            ),
        ]
        ax.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(1.15, 1))

        # Remove axes
        ax.axis('off')

        # Adjust layout to prevent legend cutoff
        plt.tight_layout()

        # Save the figure
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        plt.savefig(
            str(output_path),
            format='png',
            dpi=dpi,
            bbox_inches='tight',
            facecolor='white',
            edgecolor='none',
        )
        plt.close()

        logger.info(f'Graph visualization saved to: {output_path}')

    def _get_node_type(self, node) -> str:
        """Helper method to determine node type for visualization."""
        if isinstance(node, StartNode):
            return 'start'
        elif isinstance(node, EndNode):
            return 'end'
        elif isinstance(node, Agent):
            return 'agent'
        elif isinstance(node, Tool):
            return 'tool'
        elif isinstance(node, ForEachNode):
            return 'foreach'
        elif isinstance(node, AriumNode):
            return 'arium'
        else:
            return 'unknown'
