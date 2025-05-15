from router import Router
from packet import Packet
import json

class DVrouter(Router):
    """Distance vector routing protocol implementation with JSON-serialized content."""

    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0
        # Neighbors: port -> (neighbor_addr, cost)
        self.neighbors = {}
        # Our distance vector: dest_addr -> cost
        self.dv = {addr: 0}
        # Distance vectors received from neighbors: neighbor_addr -> {dest: cost}
        self.dv_from_neighbors = {}
        # Forwarding table: dest_addr -> port
        self.forwarding_table = {}

    def handle_new_link(self, port, endpoint, cost):
        """A new link has appeared: update direct cost and advertise."""
        self.neighbors[port] = (endpoint, cost)
        # Initialize empty DV for this neighbor
        self.dv_from_neighbors[endpoint] = {}
        # Update direct route
        if endpoint not in self.dv or cost < self.dv[endpoint]:
            self.dv[endpoint] = cost
            self.forwarding_table[endpoint] = port
        # Advertise updated DV
        self.send_dv_to_neighbors()

    def handle_remove_link(self, port):
        """An existing link was removed: recompute and advertise."""
        if port not in self.neighbors:
            return
        neighbor_addr, _ = self.neighbors.pop(port)
        self.dv_from_neighbors.pop(neighbor_addr, None)
        # Recompute DV and forwarding
        self.update_forwarding_table()
        # Advertise updated DV
        self.send_dv_to_neighbors()

    def handle_time(self, time_ms):
        """Periodic heartbeat to send DV."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.send_dv_to_neighbors()

    def handle_packet(self, port, packet):
        """Process incoming packets: traceroute data or routing updates."""
        if packet.is_traceroute:
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst]
                self.send(out_port, packet)
        else:
            # Routing update: content is JSON-encoded DV dict
            neighbor = packet.src_addr
            content_str = packet.content
            try:
                their_dv = json.loads(content_str)
            except (TypeError, json.JSONDecodeError):
                return
            # If changed or new, update and advertise
            if neighbor not in self.dv_from_neighbors or self.dv_from_neighbors[neighbor] != their_dv:
                self.dv_from_neighbors[neighbor] = their_dv
                self.update_forwarding_table()
                self.send_dv_to_neighbors()

    def send_dv_to_neighbors(self):
        """Serialize our DV and send to all neighbors."""
        content_str = json.dumps(self.dv)
        for port, (nbr_addr, _) in self.neighbors.items():
            pkt = Packet(Packet.ROUTING, self.addr, nbr_addr, content=content_str)
            self.send(port, pkt)

    def update_forwarding_table(self):
        """Recompute distance vector and forwarding table from neighbor-information."""
        # Start with self
        new_dv = {self.addr: 0}
        new_ft = {}
        # Include direct neighbors
        for port, (nbr, cost) in self.neighbors.items():
            if nbr not in new_dv or cost < new_dv[nbr]:
                new_dv[nbr] = cost
                new_ft[nbr] = port
        # Include paths via neighbors
        for nbr, their_dv in self.dv_from_neighbors.items():
            # Find port to nbr
            out_port = next((p for p, (addr, _) in self.neighbors.items() if addr == nbr), None)
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