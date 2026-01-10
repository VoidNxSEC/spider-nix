"""
Correlation engine for OSINT data.

Builds relationship graphs between discovered entities (domains, IPs, emails, etc.)
and provides analysis and visualization capabilities.
"""

import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

logger = logging.getLogger(__name__)


@dataclass
class Entity:
    """OSINT entity (domain, IP, email, etc.)."""

    id: str  # Unique identifier
    type: Literal["domain", "ip", "email", "url", "subdomain", "port", "technology", "cve"]
    value: str
    metadata: dict[str, Any] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)


@dataclass
class Relationship:
    """Relationship between two entities."""

    source_id: str
    target_id: str
    rel_type: str  # "resolves_to", "uses", "has_vulnerability", "hosts", etc.
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class IntelligenceGraph:
    """
    Graph of OSINT entities and relationships.

    Stores entities (nodes) and relationships (edges) for correlation analysis.
    """

    entities: dict[str, Entity] = field(default_factory=dict)
    relationships: list[Relationship] = field(default_factory=list)

    def add_entity(self, entity: Entity) -> None:
        """Add or update entity in graph."""
        if entity.id in self.entities:
            # Update last_seen
            self.entities[entity.id].last_seen = datetime.now()
            # Merge metadata
            self.entities[entity.id].metadata.update(entity.metadata)
        else:
            self.entities[entity.id] = entity

    def add_relationship(self, relationship: Relationship) -> None:
        """Add relationship to graph."""
        # Ensure both entities exist
        if relationship.source_id not in self.entities or relationship.target_id not in self.entities:
            logger.warning(
                f"Cannot add relationship: entities {relationship.source_id} "
                f"or {relationship.target_id} not found"
            )
            return

        self.relationships.append(relationship)

    def get_entity(self, entity_id: str) -> Entity | None:
        """Get entity by ID."""
        return self.entities.get(entity_id)

    def get_relationships(self, entity_id: str, rel_type: str | None = None) -> list[Relationship]:
        """
        Get relationships for an entity.

        Args:
            entity_id: Entity ID
            rel_type: Filter by relationship type

        Returns:
            List of relationships
        """
        results = []
        for rel in self.relationships:
            if rel.source_id == entity_id or rel.target_id == entity_id:
                if rel_type is None or rel.rel_type == rel_type:
                    results.append(rel)
        return results

    def get_connected_entities(self, entity_id: str) -> list[Entity]:
        """Get all entities connected to given entity."""
        connected_ids = set()

        for rel in self.relationships:
            if rel.source_id == entity_id:
                connected_ids.add(rel.target_id)
            elif rel.target_id == entity_id:
                connected_ids.add(rel.source_id)

        return [self.entities[eid] for eid in connected_ids if eid in self.entities]

    def export_json(self) -> str:
        """Export graph as JSON."""
        return json.dumps(
            {
                "entities": [
                    {
                        "id": e.id,
                        "type": e.type,
                        "value": e.value,
                        "metadata": e.metadata,
                        "first_seen": e.first_seen.isoformat(),
                        "last_seen": e.last_seen.isoformat(),
                    }
                    for e in self.entities.values()
                ],
                "relationships": [
                    {
                        "source": r.source_id,
                        "target": r.target_id,
                        "type": r.rel_type,
                        "metadata": r.metadata,
                        "timestamp": r.timestamp.isoformat(),
                    }
                    for r in self.relationships
                ],
            },
            indent=2,
        )

    def export_graphviz(self) -> str:
        """
        Export graph in Graphviz DOT format.

        Can be rendered with: dot -Tpng graph.dot -o graph.png
        """
        lines = ["digraph OSINT {", "  rankdir=LR;", "  node [shape=box];", ""]

        # Nodes
        for entity_id, entity in self.entities.items():
            label = f"{entity.type}\\n{entity.value[:30]}"
            color = self._get_node_color(entity.type)
            lines.append(f'  "{entity_id}" [label="{label}", fillcolor="{color}", style=filled];')

        lines.append("")

        # Edges
        for rel in self.relationships:
            label = rel.rel_type.replace("_", " ")
            lines.append(f'  "{rel.source_id}" -> "{rel.target_id}" [label="{label}"];')

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _get_node_color(entity_type: str) -> str:
        """Get color for entity type."""
        colors = {
            "domain": "lightblue",
            "subdomain": "lightcyan",
            "ip": "lightgreen",
            "email": "lightyellow",
            "url": "lightgray",
            "port": "lightpink",
            "technology": "plum",
            "cve": "red",
        }
        return colors.get(entity_type, "white")

    def get_stats(self) -> dict[str, Any]:
        """Get graph statistics."""
        entity_counts = defaultdict(int)
        for entity in self.entities.values():
            entity_counts[entity.type] += 1

        rel_counts = defaultdict(int)
        for rel in self.relationships:
            rel_counts[rel.rel_type] += 1

        return {
            "total_entities": len(self.entities),
            "total_relationships": len(self.relationships),
            "entity_breakdown": dict(entity_counts),
            "relationship_breakdown": dict(rel_counts),
        }


class CorrelationEngine:
    """
    Main correlation engine.

    Processes OSINT data and builds intelligence graphs.
    """

    def __init__(self):
        self.graph = IntelligenceGraph()

    def process_dns_results(self, domain: str, dns_records: dict) -> None:
        """
        Process DNS enumeration results.

        Args:
            domain: Domain name
            dns_records: DNS records by type
        """
        # Add domain entity
        domain_entity = Entity(
            id=f"domain:{domain}",
            type="domain",
            value=domain,
        )
        self.graph.add_entity(domain_entity)

        # Process A records (IP addresses)
        for a_record in dns_records.get("A", []):
            ip_entity = Entity(
                id=f"ip:{a_record.value}",
                type="ip",
                value=a_record.value,
                metadata={"ttl": a_record.ttl},
            )
            self.graph.add_entity(ip_entity)

            # Create relationship
            self.graph.add_relationship(
                Relationship(
                    source_id=domain_entity.id,
                    target_id=ip_entity.id,
                    rel_type="resolves_to",
                    metadata={"record_type": "A"},
                )
            )

        # Process MX records
        for mx_record in dns_records.get("MX", []):
            mx_domain = mx_record.value.split()[-1]  # Extract domain from "priority domain"
            mx_entity = Entity(
                id=f"domain:{mx_domain}",
                type="domain",
                value=mx_domain,
            )
            self.graph.add_entity(mx_entity)

            self.graph.add_relationship(
                Relationship(
                    source_id=domain_entity.id,
                    target_id=mx_entity.id,
                    rel_type="mail_server",
                    metadata={"record_type": "MX"},
                )
            )

    def process_subdomain_results(self, domain: str, subdomains: list) -> None:
        """
        Process subdomain enumeration results.

        Args:
            domain: Base domain
            subdomains: List of SubdomainResult objects
        """
        domain_entity = Entity(
            id=f"domain:{domain}",
            type="domain",
            value=domain,
        )
        self.graph.add_entity(domain_entity)

        for subdomain_result in subdomains:
            # Add subdomain entity
            subdomain_entity = Entity(
                id=f"subdomain:{subdomain_result.subdomain}",
                type="subdomain",
                value=subdomain_result.subdomain,
                metadata={"source": subdomain_result.source},
            )
            self.graph.add_entity(subdomain_entity)

            # Relationship to parent domain
            self.graph.add_relationship(
                Relationship(
                    source_id=domain_entity.id,
                    target_id=subdomain_entity.id,
                    rel_type="has_subdomain",
                )
            )

            # Process IP addresses
            for ip in subdomain_result.ip_addresses:
                ip_entity = Entity(
                    id=f"ip:{ip}",
                    type="ip",
                    value=ip,
                )
                self.graph.add_entity(ip_entity)

                self.graph.add_relationship(
                    Relationship(
                        source_id=subdomain_entity.id,
                        target_id=ip_entity.id,
                        rel_type="resolves_to",
                    )
                )

    def process_port_scan(self, host: str, scan_result) -> None:
        """
        Process port scan results.

        Args:
            host: Target host (IP or domain)
            scan_result: ScanResult object
        """
        # Determine entity type
        entity_type = "ip" if host.replace(".", "").isdigit() else "domain"

        host_entity = Entity(
            id=f"{entity_type}:{host}",
            type=entity_type,
            value=host,
        )
        self.graph.add_entity(host_entity)

        # Process open ports
        for port_result in scan_result.results:
            if port_result.state == "open":
                port_entity = Entity(
                    id=f"port:{host}:{port_result.port}",
                    type="port",
                    value=f"{port_result.port}/{port_result.protocol}",
                    metadata={
                        "service": port_result.service,
                        "version": port_result.version,
                        "banner": port_result.banner,
                    },
                )
                self.graph.add_entity(port_entity)

                self.graph.add_relationship(
                    Relationship(
                        source_id=host_entity.id,
                        target_id=port_entity.id,
                        rel_type="has_open_port",
                    )
                )

    def process_tech_stack(self, url: str, tech_stack: list) -> None:
        """
        Process technology detection results.

        Args:
            url: URL scanned
            tech_stack: List of TechStack objects
        """
        url_entity = Entity(
            id=f"url:{url}",
            type="url",
            value=url,
        )
        self.graph.add_entity(url_entity)

        for tech in tech_stack:
            tech_entity = Entity(
                id=f"technology:{tech.name}",
                type="technology",
                value=tech.name,
                metadata={"category": tech.category, "version": tech.version},
            )
            self.graph.add_entity(tech_entity)

            self.graph.add_relationship(
                Relationship(
                    source_id=url_entity.id,
                    target_id=tech_entity.id,
                    rel_type="uses_technology",
                    metadata={"confidence": tech.confidence},
                )
            )

    def process_vulnerabilities(self, target: str, issues: list) -> None:
        """
        Process vulnerability scan results.

        Args:
            target: Target URL/host
            issues: List of SecurityIssue objects
        """
        target_entity = Entity(
            id=f"url:{target}",
            type="url",
            value=target,
        )
        self.graph.add_entity(target_entity)

        for issue in issues:
            if issue.cve_id:
                # Create CVE entity
                cve_entity = Entity(
                    id=f"cve:{issue.cve_id}",
                    type="cve",
                    value=issue.cve_id,
                    metadata={
                        "severity": issue.severity,
                        "description": issue.description,
                    },
                )
                self.graph.add_entity(cve_entity)

                self.graph.add_relationship(
                    Relationship(
                        source_id=target_entity.id,
                        target_id=cve_entity.id,
                        rel_type="has_vulnerability",
                        metadata={"severity": issue.severity},
                    )
                )

    def generate_report(self) -> dict[str, Any]:
        """
        Generate comprehensive OSINT report.

        Returns:
            Report with statistics and key findings
        """
        stats = self.graph.get_stats()

        # Find high-risk entities (those with CVE relationships)
        vulnerable_entities = set()
        for rel in self.graph.relationships:
            if rel.rel_type == "has_vulnerability":
                vulnerable_entities.add(rel.source_id)

        # Find critical technologies
        tech_usage = defaultdict(int)
        for rel in self.graph.relationships:
            if rel.rel_type == "uses_technology":
                target = self.graph.get_entity(rel.target_id)
                if target:
                    tech_usage[target.value] += 1

        return {
            "generated_at": datetime.now().isoformat(),
            "statistics": stats,
            "vulnerable_count": len(vulnerable_entities),
            "top_technologies": dict(sorted(tech_usage.items(), key=lambda x: x[1], reverse=True)[:10]),
            "graph_export": {
                "json_available": True,
                "graphviz_available": True,
            },
        }
