from router import Router
from packet import Packet
import json


class DVrouter(Router):
    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        self.neighbors = {}
        self.dv = {addr: 0}
        self.dv_from_neighbors = {}
        self.forwarding_table = {}

    def handle_new_link(self, port, endpoint, cost):
        self.neighbors[port] = (endpoint, cost)
        self.dv_from_neighbors[endpoint] = 
        if endpoint not in self.dv or cost < self.dv[endpoint]:
            self.dv[endpoint] = cost
            self.forwarding_table[endpoint] = port
        self.send_dv_to_neighbors()

    def handle_remove_link(self, port):
        if port not in self.neighbors:
            return
        neighbor_addr, _ = self.neighbors.pop(port)
        self.dv_from_neighbors.pop(neighbor_addr, None)
        self.update_forwarding_table()
        self.send_dv_to_neighbors()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.send_dv_to_neighbors()

    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst]
                self.send(out_port, packet)
        else:
            neighbor = packet.src_addr
            content_str = packet.content
            try:
                their_dv = json.loads(content_str)
            except (TypeError, json.JSONDecodeError):
                return
            if neighbor not in self.dv_from_neighbors or self.dv_from_neighbors[neighbor] != their_dv:
                self.dv_from_neighbors[neighbor] = their_dv
                self.update_forwarding_table()
                self.send_dv_to_neighbors()

    def send_dv_to_neighbors(self):
        content_str = json.dumps(self.dv)
        for port, (nbr_addr, _) in self.neighbors.items():
            pkt = Packet(Packet.ROUTING, self.addr,
                         nbr_addr, content=content_str)
            self.send(port, pkt)

    def update_forwarding_table(self):
        new_dv = {self.addr: 0}
        new_ft = {}
        for port, (nbr, cost) in self.neighbors.items():
            if nbr not in new_dv or cost < new_dv[nbr]:
                new_dv[nbr] = cost
                new_ft[nbr] = port

        for nbr, their_dv in self.dv_from_neighbors.items():
            out_port = next(
                (p for p, (addr, _) in self.neighbors.items() if addr == nbr), None)
            if out_port is None:
                continue
            cost_to_nbr = self.neighbors[out_port][1]
            for dest, dcost in their_dv.items():
                if dest == self.addr:
                    continue
                total = cost_to_nbr + dcost
                if dest not in new_dv or total < new_dv[dest]:
                    new_dv[dest] = total
                    new_ft[dest] = out_port
        self.dv = new_dv
        self.forwarding_table = new_ft

    def __repr__(self):
        return f"DVrouter(addr={self.addr}, dv={self.dv})"
