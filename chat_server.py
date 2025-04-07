import base64
import ssl
import threading

import select
import sys
import socket
import argparse

from utils import *

SERVER_HOST = 'localhost'


def commands(server):
    print('Type "help" for a list of commands')
    while server.running:
        cmd = sys.stdin.readline().strip().lower()
        if cmd == 'help':
            print('Commands:')
            print('list: List all connected clients')
            print('quit: Shutdown the server')
        elif cmd == 'list':
            print(server.clientMap.values())
        elif cmd == 'quit':
            server.running = False
            for output in server.outputs:
                server.remove_client(output)
            server.server.close()
            sys.exit(0)
        else:
            print('Unknown command')


class ChatServer:
    def __init__(self, port, backlog=5):
        # Initialize client registry
        self.clients = 0
        self.userMap = {}
        self.signed_in = []
        self.clientMap = {}

        # Initialize input and output socket lists
        self.inputs = []
        self.outputs = []

        # Create SSL context
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        self.context.load_cert_chain(certfile="cert.pem", keyfile="cert.pem")
        self.context.load_verify_locations('cert.pem')
        self.context.set_ciphers('AES128-SHA')

        # Create a TCP socket
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((SERVER_HOST, port))
        self.server.listen(backlog)

        # Wrap the socket with SSL
        self.server = self.context.wrap_socket(self.server, server_side=True)

        # Add server socket to the list of readable connections
        self.inputs.append(self.server)
        print(f'Server listening to port: {port} ...')

    def get_client_name(self, client):
        info = self.clientMap[client]
        name = info[1]
        return name

    def login(self, client, address, cname):
        # Register the client
        self.clients += 1
        send(client, 'CLIENT' + ':' + str(address[1]))
        self.inputs.append(client)
        self.clientMap[client] = (address, cname)
        self.outputs.append(client)

        # Flag user as signed in
        self.signed_in.append(cname)

        # Send joining information to other clients
        msg = f'({self.get_client_name(client)}) has joined the chat'
        for output in self.outputs:
            send(output, msg)

    def remove_client(self, sock):
        # De-register client
        self.clients -= 1
        sock.close()
        self.inputs.remove(sock)
        self.outputs.remove(sock)
        self.signed_in.remove(self.clientMap.pop(sock)[1])

    def run(self):
        self.running = True

        # Start background thread to handle commands
        threading.Thread(target=commands, args=(self,)).start()

        while self.running:
            # Get the list sockets which are ready to be read through select
            try:
                readable, writeable, exceptional = select.select(self.inputs, self.outputs, [])
            except select.error as e:
                print('Error: ', e)
                break
            # Handle inputs
            for sock in readable:
                try:
                    sys.stdout.flush()
                    # traffic from server socket is a new connection
                    if sock == self.server:
                        client, address = self.server.accept()
                        print(f'Chat server: got connection ({self.clients}) from {address}')

                        # Read base64 encoded data and decode it
                        data = receive(client)
                        [caction, cname, cpassword] = data.split(b':')
                        caction = base64.b64decode(caction).decode()
                        cname = base64.b64decode(cname).decode()
                        cpassword = base64.b64decode(cpassword).decode()

                        if caction == 'login':
                            # filter out non-existent usernames, already logged-in users, and wrong passwords
                            if cname not in self.userMap:
                                send(client, 'ERROR' + ':' + 'Sorry, user not found.')
                            elif cname in self.signed_in:
                                send(client, 'ERROR' + ':' + 'Sorry, user already logged in.')
                            elif self.userMap[cname] != cpassword:
                                send(client, 'ERROR' + ':' + 'Sorry, wrong password.')
                            else:
                                server.login(client, address, cname)
                        else:
                            # filter out taken usernames and 'all' since it is a reserved keyword
                            if cname not in self.userMap and cname.lower() != 'all':
                                # Register the new user
                                self.userMap.update({cname: cpassword})
                                # Log the client in to the new user
                                server.login(client, address, cname)
                            else:
                                send(client, 'ERROR' + ':' + 'Sorry, name taken.')
                    else:
                        # Process data from an existing client
                            data = receive(sock)
                            if data:
                                # Get base64 encoded data and decode it
                                [target, message] = data.split(b':')
                                target = base64.b64decode(target).decode()
                                message = base64.b64decode(message).decode()

                                msg = f'({self.get_client_name(sock)} to {target})> {message}'
                                if target == 'all':
                                    # Send message to all clients except the sender
                                    for output in self.outputs:
                                        if output != sock:
                                            send(output, msg)
                                else:
                                    # Try to send message to the target client
                                    found = False
                                    for client, info in self.clientMap.items():
                                        if info[1] == target:
                                            send(client, msg)
                                            found = True
                                    # Send error message if target not found
                                    if not found:
                                        send(sock, 'Sorry, user not found.')
                            else:
                                # No data means that the client has closed the connection
                                print(f'Chat server: {sock.fileno()} hung up')

                                # Sending client leaving information to others
                                msg = f'({self.get_client_name(sock)}) has left the chat.'
                                for output in self.outputs:
                                    send(output, msg)

                                # Remove the socket
                                self.remove_client(sock)
                except socket.error as e:
                    if(sock != self.server):
                        # Remove the socket that's broken
                        self.remove_client(sock)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Socket Server Example with Select')
    parser.add_argument('--port', action="store",
                        dest="port", type=int, required=True)
    given_args = parser.parse_args()
    port = given_args.port

    server = ChatServer(port)
    server.run()

