from router import Router
from packet import Packet
import heapq
import json


class LSrouter(Router):

    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        self.lsdb = {}
        self.neighbors = {}
        self.forwarding_table = {}
        self.seq_num = 0

    def handle_new_link(self, port, endpoint, cost):
        self.neighbors[port] = (endpoint, cost)
        self.seq_num += 1
        self.advertise_lsp()

    def handle_remove_link(self, port):
        if port in self.neighbors:
            del self.neighbors[port]
            self.seq_num += 1
            self.advertise_lsp()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.seq_num += 1
            self.advertise_lsp()

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst][0]
                self.send(out_port, packet)
        else:
            try:
                origin, seq, links = json.loads(packet.content)
            except (TypeError, json.JSONDecodeError, ValueError):
                return
            prev = self.lsdb.get(origin)
            if prev is None or seq > prev[0]:
                self.lsdb[origin] = (seq, links.copy())
                self.run_dijkstra()
                for p, (nbr, _) in self.neighbors.items():
                    if p != port:
                        content_str = json.dumps((origin, seq, links))
                        pkt = Packet(Packet.ROUTING, self.addr,
                                     nbr, content=content_str)
                        self.send(p, pkt)

    def advertise_lsp(self):
        links = {nbr: cost for (_, (nbr, cost)) in self.neighbors.items()}
        self.lsdb[self.addr] = (self.seq_num, links.copy())
        content_str = json.dumps((self.addr, self.seq_num, links))
        for port, (nbr, _) in self.neighbors.items():
            pkt = Packet(Packet.ROUTING, self.addr, nbr, content=content_str)
            self.send(port, pkt)
        self.run_dijkstra()

    def run_dijkstra(self):
        graph = {router: links.copy()
                 for router, (_, links) in self.lsdb.items()}
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

        self.forwarding_table.clear()
        for dest, total_cost in dist.items():
            if dest == self.addr:
                continue
            next_hop = dest
            while prev.get(next_hop) != self.addr:
                next_hop = prev.get(next_hop)
                if next_hop is None:
                    break
            if next_hop is None:
                continue
            for port, (nbr, _) in self.neighbors.items():
                if nbr == next_hop:
                    self.forwarding_table[dest] = (port, total_cost)
                    break

    def __repr__(self):
        return f"LSrouter(addr={self.addr}, ft={self.forwarding_table})"
