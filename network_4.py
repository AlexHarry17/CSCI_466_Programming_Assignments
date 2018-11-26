import math
import pprint
import queue
import threading
from collections import OrderedDict, defaultdict
from time import sleep


## wrapper class for a queue of packets
class Interface:
    ## @param maxsize - the maximum size of the queue storing packets
    def __init__(self, maxsize=0):
        self.in_queue = queue.Queue(maxsize)
        self.out_queue = queue.Queue(maxsize)

    ##get packet from the queue interface
    # @param in_or_out - use 'in' or 'out' interface
    def get(self, in_or_out):
        try:
            if in_or_out == 'in':
                pkt_S = self.in_queue.get(False)
                # if pkt_S is not None:
                #     print('getting packet from the IN queue')
                return pkt_S
            else:
                pkt_S = self.out_queue.get(False)
                # if pkt_S is not None:
                #     print('getting packet from the OUT queue')
                return pkt_S
        except queue.Empty:
            return None

    ##put the packet into the interface queue
    # @param pkt - Packet to be inserted into the queue
    # @param in_or_out - use 'in' or 'out' interface
    # @param block - if True, block until room in queue, if False may throw queue.Full exception
    def put(self, pkt, in_or_out, block=False):
        if in_or_out == 'out':
            # print('putting packet in the OUT queue')
            self.out_queue.put(pkt, block)
        else:
            # print('putting packet in the IN queue')
            self.in_queue.put(pkt, block)


## Implements a network layer packet.
class NetworkPacket:
    ## packet encoding lengths
    dst_S_length = 5
    prot_S_length = 1

    ##@param dst: address of the destination host
    # @param data_S: packet payload
    # @param prot_S: upper layer protocol for the packet (data, or control)
    def __init__(self, dst, prot_S, data_S):
        self.dst = dst
        self.data_S = data_S
        self.prot_S = prot_S

    ## called when printing the object
    def __str__(self):
        return self.to_byte_S()

    ## convert packet to a byte string for transmission over links
    def to_byte_S(self):
        byte_S = str(self.dst).zfill(self.dst_S_length)
        if self.prot_S == 'data':
            byte_S += '1'
        elif self.prot_S == 'control':
            byte_S += '2'
        else:
            raise ('%s: unknown prot_S option: %s' % (self, self.prot_S))
        byte_S += self.data_S
        return byte_S

    ## extract a packet object from a byte string
    # @param byte_S: byte string representation of the packet
    @classmethod
    def from_byte_S(self, byte_S):
        dst = byte_S[0: NetworkPacket.dst_S_length].strip('0')
        prot_S = byte_S[NetworkPacket.dst_S_length: NetworkPacket.dst_S_length + NetworkPacket.prot_S_length]
        if prot_S == '1':
            prot_S = 'data'
        elif prot_S == '2':
            prot_S = 'control'
        else:
            raise ('%s: unknown prot_S field: %s' % (self, prot_S))
        data_S = byte_S[NetworkPacket.dst_S_length + NetworkPacket.prot_S_length:]
        return self(dst, prot_S, data_S)


## Implements a network host for receiving and transmitting data
class Host:

    ##@param addr: address of this node represented as an integer
    def __init__(self, addr):
        self.addr = addr
        self.intf_L = [Interface()]
        self.stop = False  # for thread termination

    ## called when printing the object
    def __str__(self):
        return self.addr

    ## create a packet and enqueue for transmission
    # @param dst: destination address for the packet
    # @param data_S: data being transmitted to the network layer
    def udt_send(self, dst, data_S):
        p = NetworkPacket(dst, 'data', data_S)
        print('%s: sending packet "%s"' % (self, p))
        self.intf_L[0].put(p.to_byte_S(), 'out')  # send packets always enqueued successfully

    ## receive packet from the network layer
    def udt_receive(self):
        pkt_S = self.intf_L[0].get('in')
        if pkt_S is not None:
            print('%s: received packet "%s"' % (self, pkt_S))

    ## thread target for the host to keep receiving data
    def run(self):
        print(threading.currentThread().getName() + ': Starting')
        while True:
            # receive data arriving to the in interface
            self.udt_receive()
            # terminate
            if (self.stop):
                print(threading.currentThread().getName() + ': Ending')
                return


## Implements a multi-interface router
class Router:

    ##@param name: friendly router name for debugging
    # @param cost_D: cost table to neighbors {neighbor: {interface: cost}}
    # @param max_queue_size: max queue length (passed to Interface)
    def __init__(self, name, cost_D, max_queue_size):
        self.stop = False  # for thread termination
        self.name = name
        # create a list of interfaces
        self.intf_L = [Interface(max_queue_size) for _ in range(len(cost_D))]
        # save neighbors and interfeces on which we connect to them
        self.cost_D = cost_D  # {neighbor: {interface: cost}}
        self.rt_tbl_D = cost_D.copy()
        self.total_rt = defaultdict(dict)
        for n_name, n_info in self.cost_D.items():
            for interface, cost in n_info.items():
                self.total_rt[name][n_name] = [cost]
        # self.rt_tbl_D = {dest:{self.name: cost for key,cost in cost_D[dest].items()} for dest in cost_D} #{destination: {name: {cost}}
        # self.rt_tbl_D[self.name] = {self.name: 0}   #setting own name to name in the dictionary
        print('%s: Initialized routing table' % self)
        self.print_routes()

    ## called when printing the object
    def __str__(self):
        return self.name

    ## look through the content of incoming interfaces and
    # process data and control packets
    def process_queues(self):
        for i in range(len(self.intf_L)):
            pkt_S = None
            # get packet from interface i
            pkt_S = self.intf_L[i].get('in')
            # if packet exists make a forwarding decision
            if pkt_S is not None:
                p = NetworkPacket.from_byte_S(pkt_S)  # parse a packet out
                if p.prot_S == 'data':
                    self.forward_packet(p, i)
                elif p.prot_S == 'control':
                    self.update_routes(p, i)
                else:
                    raise Exception('%s: Unknown packet type in packet %s' % (self, p))

    ## forward the packet according to the routing table
    #  @param p Packet to forward
    #  @param i Incoming interface number for packet p
    def forward_packet(self, p, i):
        try:
            neighbor = list(self.cost_D.keys())  # list of key values for router's neighbors
            # print("Routing table: ", self.rt_tbl_D, "in interface: ", i)
            # print(self, "....... Neighbor: ", neighbor, "out int: ", out_int )
            # print("route table: ", self.rt_tbl_D[neighbor[i]], ".............................",neighbor, "self: ", self)
            out_int = math.inf  # starts out interface at inf
            # print("out int: ", out_int)
            weight = math.inf  # sets initial weight to inf
            for k in range(len(neighbor)):  # loops through routers neighbors
                route_table = self.rt_tbl_D
                keys = list(self.rt_tbl_D[neighbor[k]].keys())  # list of keys
                temp_rt_table = self.rt_tbl_D[
                    neighbor[k]]  # this is the routing table of the neighbor that is being looked at
                for j in range(
                        len(keys)):  # loops through neighbors keys.  Not extremely necessary for this application
                    if temp_rt_table[keys[j]] <= weight and i != keys[
                        j]:  # enters if the weight of the link is less than current weight, Doesn't enter if checking incoming interface
                        weight = temp_rt_table[keys[j]]  # sets weight for later comparison
                        out_int = keys[j]  # sets outgoing interface

            # forwarding table to find the appropriate outgoing interface
            # for now we assume the outgoing interface is 1
            self.intf_L[out_int].put(p.to_byte_S(), 'out', True)
            print('%s: forwarding packet "%s" from interface %d to %d' % \
                  (self, p, i, out_int))
        except queue.Full:
            print('%s: packet "%s" lost on interface %d' % (self, p, i))
            pass

    ## send out route update
    # must encode packet - /// is sending router, / seperates the link and cost, // seperates routes
    # @param i Interface number on which to send out a routing update
    def send_routes(self, i):
        route = self.name + "///"  # encoding the name of the sending router
        for k, v in self.rt_tbl_D.items():  # for each key,value pair in the routing table
            for link, cost in v.items():  # for each link, and cost in the above value
                # print("link", link)
                route += str(k) + "/" + str(link) + "/" + str(
                    cost) + "//"  # append the key (destination), link (sending router), and cost
        # print(self.rt_tbl_D)
        # print(route)
        # create a routing table update packet
        p = NetworkPacket(0, 'control', route)
        try:
            print('%s: sending routing update "%s" from interface %d' % (self, p, i))
            self.intf_L[i].put(p.to_byte_S(), 'out', True)
        except queue.Full:
            print('%s: packet "%s" lost on interface %d' % (self, p, i))
            pass

    ## forward the packet according to the routing table
    #  @param p Packet containing routing information
    def update_routes(self, p, i):
        made_update = False  # variable to keep track of whether we've updated

        packet_table = p.data_S.split("///")  # break packet down into components

        table_routes = packet_table[1].split("//")  # break packet into individual routes

        length = len(table_routes)
        table_routes = table_routes[:length - 1]  # remove last route as it's invalid ('')

        title = packet_table[0]  # save title that's at beginning of packet
        for table_route in table_routes:  # for each route in the packet_table
            route = table_route.split("/")

            self.total_rt[title][route[0]] = [int(route[2])]  # create new entry in  global routing table

            if route[0] == self.name:  # if the route is this routers
                neighbor_inf = list(self.cost_D[title].keys())  # neighbor interace, is itself, but is needed
                self.rt_tbl_D[route[0]] = {int(neighbor_inf[0]): 0}  # set the r_tbl_D to 0
                self.total_rt[self.name][route[0]] = [
                    0]  # update dictionary table of routes with distance (0 since it's its self)
                continue

            if route[0] not in self.cost_D and route[0] not in self.rt_tbl_D:  # route not a neighbor or in table
                neighbor_D = list(self.cost_D[title].values())  # neighbor distance
                neighbor_inf = list(self.cost_D[title].keys())  # neighbor interaface
                self.rt_tbl_D[route[0]] = {int(neighbor_inf[0]): int(route[2]) + neighbor_D[
                    0]}  # distance to new node is the distance to neighbor + distance from neighbor to node
                self.total_rt[self.name][route[0]] = [
                    int(route[2]) + neighbor_D[0]]  # update dictionary table of routes with distance
                made_update = True  # updated table

            elif route[0] not in self.cost_D and route[
                0] in self.rt_tbl_D:  # route not a neighbor but is in table already
                neighbor_D = list(self.cost_D[title].values())  # neighbor distance
                neighbor_inf = list(self.cost_D[title].keys())  # neighbor interface
                available_D = list(self.rt_tbl_D[route[0]].values())  # the current distance in the table
                if available_D[0] > neighbor_D[0] + int(route[2]):  # if there is a shorter distance available
                    self.rt_tbl_D[route[0]] = {
                        int(neighbor_inf[0]): int(route[2]) + neighbor_D[0]}  # calculate new distance
                    self.total_rt[self.name][route[0]] = [
                        int(route[2]) + neighbor_D[0]]  # update dictionary table of routes with distance
                    made_update = True  # was updated

        if made_update:  # if we've updated, tell all neighbors
            for neighbor_name, neighbor_info in self.cost_D.items():
                for interface, cost in neighbor_info.items():
                    if 'H' not in neighbor_name:  # if neighbor is not a host
                        self.send_routes(interface)

            sleep(2)
            self.print_routes()
        print('%s: Received routing update %s from interface %d' % (self, p, i))

    ## Print routing table
    def print_routes(self):
        outline = '-'
        print('\n')
        sort = OrderedDict(sorted(self.total_rt.items()))  # sorting the table so the table is consistent on all routers

        line = self.name
        for i, j in sort.items():  # for each k,v pair in the sorted table, print outline
            outline += "------------"
            line += ("   |   " + str(i))
            # print("\t" + str(i), end='')
        print(line, "   |")
        print(outline)

        interfaces = []  # creat empty list of hosts / routers for quick access to names
        for i, j in sort.items():  # for each router / host in the routing table, append the name of that router / host to the list
            for link, cost in j.items():
                if not link in interfaces:
                    interfaces.append(link)
        interfaces = sorted(interfaces)

        for interface in interfaces:  # for each router / host in the network
            print(str(interface) + "   |   ", end='')  # print the name of the router / host
            for i, j in sort.items():  # for each k/v pair in the host, print the costs in the table
                if not interface in j.keys():
                    print(" ~    |  ", end='')
                else:
                    for link, cost in j.items():
                        if link == interface:
                            print(str(cost) + "   |  ", end='')  # printing the cost throughout the table
            print('\n')

    ## thread target for the host to keep forwarding data
    def run(self):
        print(threading.currentThread().getName() + ': Starting')
        while True:
            self.process_queues()
            if self.stop:
                print(threading.currentThread().getName() + ': Ending')
                return
