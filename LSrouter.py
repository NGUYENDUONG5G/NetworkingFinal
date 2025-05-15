from router import Router
from packet import Packet
import heapq
import json

class LSrouter(Router):
    """Link State routing protocol implementation with JSON-serialized LSPs."""

    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        # Link State Database: addr -> (seq_num, {neighbor: cost})
        self.lsdb = {}
        # Neighbors: port -> (neighbor_addr, cost)
        self.neighbors = {}
        # Forwarding table: dest -> (port, cost)
        self.forwarding_table = {}
        # Sequence number for own LSP
        self.seq_num = 0

    def handle_new_link(self, port, endpoint, cost):
        """Called when a new link is added to this router."""
        self.neighbors[port] = (endpoint, cost)
        self.seq_num += 1
        self.advertise_lsp()

    def handle_remove_link(self, port):
        """Called when an existing link is removed from this router."""
        if port in self.neighbors:
            del self.neighbors[port]
            self.seq_num += 1
            self.advertise_lsp()

    def handle_time(self, time_ms):
        """Periodic heartbeat to refresh and flood LSP."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.seq_num += 1
            self.advertise_lsp()

    def handle_packet(self, port, packet):
        """Process incoming packet: traceroute or LSP update."""
        if packet.is_traceroute:
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst][0]
                self.send(out_port, packet)
        else:
            # Routing packet: JSON string content
            try:
                origin, seq, links = json.loads(packet.content)
            except (TypeError, json.JSONDecodeError, ValueError):
                return
            prev = self.lsdb.get(origin)
            if prev is None or seq > prev[0]:
                # Update LSDB
                self.lsdb[origin] = (seq, links.copy())
                # Recompute routes
                self.run_dijkstra()
                # Flood LSP to neighbors except source
                for p, (nbr, _) in self.neighbors.items():
                    if p != port:
                        content_str = json.dumps((origin, seq, links))
                        pkt = Packet(Packet.ROUTING, self.addr, nbr, content=content_str)
                        self.send(p, pkt)

    def advertise_lsp(self):
        """Build and flood this router's LSP (as JSON) to all neighbors."""
        # Prepare link-state info
        links = {nbr: cost for (_, (nbr, cost)) in self.neighbors.items()}
        # Update own LSDB
        self.lsdb[self.addr] = (self.seq_num, links.copy())
        # Serialize and send to neighbors
        content_str = json.dumps((self.addr, self.seq_num, links))
        for port, (nbr, _) in self.neighbors.items():
            pkt = Packet(Packet.ROUTING, self.addr, nbr, content=content_str)
            self.send(port, pkt)
        # Recompute forwarding after flooding
        self.run_dijkstra()

    def run_dijkstra(self):
        """Compute shortest paths from self.addr using current LSDB."""
        # Build graph: router -> {neighbor: cost}
        graph = {router: links.copy() for router, (_, links) in self.lsdb.items()}
        dist = {self.addr: 0}
        prev = {}
        heap = [(0, self.addr)]
        visited = set()

        while heap:
            d, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)
            for v, w in graph.get(u, {}).items():
                nd = d + w
                if v not in dist or nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(heap, (nd, v))

        # Rebuild forwarding table: dest -> (port, cost)
        self.forwarding_table.clear()
        for dest, total_cost in dist.items():
            if dest == self.addr:
                continue
            # Trace back to next hop
            next_hop = dest
            while prev.get(next_hop) != self.addr:
                next_hop = prev.get(next_hop)
                if next_hop is None:
                    break
            if next_hop is None:
                continue
            # Find port to next_hop
            for port, (nbr, _) in self.neighbors.items():
                if nbr == next_hop:
                    self.forwarding_table[dest] = (port, total_cost)
                    break

    def __repr__(self):
        return f"LSrouter(addr={self.addr}, ft={self.forwarding_table})"