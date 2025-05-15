from router import Router
from packet import Packet

class DVrouter(Router):
    """Distance Vector routing protocol implementation."""

    def __init__(self, addr, heartbeat_time):
        super().__init__(addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        # Neighbors: port -> (neighbor_addr, cost)
        self.neighbors = {}
        # Our distance vector: dest_addr -> cost
        self.dv = {addr: 0}
        # Distance vectors from neighbors: neighbor_addr -> {dest: cost}
        self.dv_from_neighbors = {}
        # Forwarding table: dest_addr -> port
        self.forwarding_table = {}

    def handle_new_link(self, port, endpoint, cost):
        """Called when a new link is added to this router."""
        # Record neighbor
        self.neighbors[port] = (endpoint, cost)
        # Initialize neighbor's DV record
        self.dv_from_neighbors[endpoint] = {}
        # Update our own DV and forwarding entry for the direct neighbor
        if endpoint not in self.dv or cost < self.dv[endpoint]:
            self.dv[endpoint] = cost
            self.forwarding_table[endpoint] = port
        # Broadcast updated DV
        self.send_dv_to_neighbors()

    def handle_remove_link(self, port):
        """Called when an existing link is removed from this router."""
        if port not in self.neighbors:
            return
        neighbor_addr, _ = self.neighbors.pop(port)
        # Remove neighbor's DV info
        self.dv_from_neighbors.pop(neighbor_addr, None)
        # Recompute DV and forwarding
        self.update_forwarding_table()
        # Broadcast updated DV
        self.send_dv_to_neighbors()

    def handle_time(self, time_ms):
        """Called periodically with the current time in milliseconds."""
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self.send_dv_to_neighbors()

    def handle_packet(self, port, packet):
        """Process incoming packets: traceroute data or routing updates."""
        if packet.is_traceroute:
            # Data packet: forward based on table
            dst = packet.dst_addr
            if dst in self.forwarding_table:
                out_port = self.forwarding_table[dst]
                self.send(out_port, packet)
        else:
            # Routing packet: neighbor's DV
            neighbor = packet.src_addr
            their_dv = packet.content
            # Check if this DV is new or changed
            if (neighbor not in self.dv_from_neighbors) or (self.dv_from_neighbors[neighbor] != their_dv):
                self.dv_from_neighbors[neighbor] = their_dv.copy()
                # Recompute our DV and forwarding table
                self.update_forwarding_table()
                # Broadcast updated DV to all neighbors
                self.send_dv_to_neighbors()

    def send_dv_to_neighbors(self):
        """Send our current distance vector to all neighbors."""
        for port, (nbr_addr, _) in self.neighbors.items():
            pkt = Packet(Packet.ROUTING, self.addr, nbr_addr, content=self.dv.copy())
            self.send(port, pkt)

    def update_forwarding_table(self):
        """Recompute distance vector and forwarding table from neighbor DVs."""
        # Start with self
        new_dv = {self.addr: 0}
        new_ft = {}
        # Include direct neighbors
        for port, (nbr, cost) in self.neighbors.items():
            # Ensure direct neighbor cost is in DV
            if nbr not in new_dv or cost < new_dv[nbr]:
                new_dv[nbr] = cost
                new_ft[nbr] = port
        # Consider paths via neighbors
        for nbr, their_dv in self.dv_from_neighbors.items():
            # Find port to this neighbor
            out_port = next((p for p, (addr, _) in self.neighbors.items() if addr == nbr), None)
            if out_port is None:
                continue
            cost_to_nbr = self.neighbors[out_port][1]
            for dest, c in their_dv.items():
                if dest == self.addr:
                    continue
                total = cost_to_nbr + c
                if dest not in new_dv or total < new_dv[dest]:
                    new_dv[dest] = total
                    new_ft[dest] = out_port
        self.dv = new_dv
        self.forwarding_table = new_ft

    def __repr__(self):
        return f"DVrouter(addr={self.addr}, dv={self.dv})"