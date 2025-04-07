import base64
import ssl

import select
import sys
import argparse
import threading

from utils import *

SERVER_HOST = 'localhost'


def get_and_send(client):
    # default target is all
    target = 'all'
    while True:
        data = sys.stdin.readline().strip()
        if data and data.startswith('/'):
            if data.lower() == '/quit':
                client.sock.close()
                sys.exit(1)
            elif data.lower().startswith('/help'):
                print('Commands:')
                print('/quit: Quit the chat')
                print('/all: Set target to all users')
                print('/<username>: Set target user for messages')
                print('Please note the username is case sensitive, and the user must be online')
            elif data.lower() == '/all':
                # Set the target user for messages as all
                target = 'all'
                client.prompt = f'[{client.name}@{client.addr} to: all]> '
            else:
                # Set the target user for messages as anything that follows the /
                target = data.split('/')[1]
                client.prompt = f'[{client.name}@{client.addr} to: {target}]> '

        elif data:
            # Send the message to the server encoded in base64 to prevent injection attacks as : is used as a separator
            send(client.sock,
                 base64.b64encode(target.encode()) + b':' +
                 base64.b64encode(data.encode()))
        # Print the prompt
        sys.stdout.write(client.prompt)
        sys.stdout.flush()

class ChatClient():
    """ A command line chat client using select """
    def __init__(self, port, host=SERVER_HOST):
        self.host = host
        self.port = port

        try:
            # repeat until user is successfully signed in
            signing_in = True
            while signing_in:

                # Initialize SSL context
                self.context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
                self.context.set_ciphers('AES128-SHA')

                # Create a TCP socket
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

                # Wrap the socket with SSL
                self.sock = self.context.wrap_socket(self.sock, server_hostname=host)

                # Get user input for login or register
                sys.stdout.write("Type 'LOGIN' or 'REGISTER' to start chatting: ")
                sys.stdout.flush()
                self.action = ''
                while self.action == '':
                    inputAction = sys.stdin.readline().strip()
                    if inputAction.lower() == 'login' or inputAction.lower() == 'l':
                        self.action = 'login'
                    elif inputAction.lower() == 'register' or inputAction.lower() == 'r':
                        self.action = 'register'
                    else:
                        sys.stdout.write("Invalid input. Type 'LOGIN' or 'REGISTER': ")
                        sys.stdout.flush()

                # Get non-empty user input for username and password
                self.name = ''
                while self.name == '':
                    sys.stdout.write("Username: ")
                    sys.stdout.flush()
                    self.name = sys.stdin.readline().strip()
                    if self.name == '':
                        sys.stdout.write("Username cannot be empty. Please enter a username: ")
                        sys.stdout.flush()

                self.password = ''
                while self.password == '':
                    sys.stdout.write("Password: ")
                    sys.stdout.flush()
                    self.password = sys.stdin.readline().strip()
                    if self.password == '':
                        sys.stdout.write("Password cannot be empty. Please enter a password: ")
                        sys.stdout.flush()

                # Connect to the server
                self.sock.connect((host, self.port))

                # Send base64 encoded login or register information to the server to prevent injection attacks as
                # : is used as a separator
                send(self.sock,
                     base64.b64encode(self.action.encode()) + b':' +
                     base64.b64encode(self.name.encode()) + b':' +
                     base64.b64encode(self.password.encode()))

                # Receive response from server
                data = receive(self.sock)
                [header, body] = data.split(':')

                # Check if response is an error
                if header == 'ERROR':
                    print(f'Error: {body}')
                    self.sock.close()
                else:
                    # Contains client address, set it
                    self.addr = body

                    # Set the prompt with default target as all
                    self.prompt = f'[{self.name}@{self.addr} to: all]> '

                    # Inform user of successful connection
                    print('Connected to chat server @ port', self.port, 'as', self.name)
                    print('Type /help for a list of commands')

                    # Break out of the loop
                    signing_in = False
        except socket.error as e:
            print('Error: ', e)
            print(f'Failed to connect to chat server @ port {self.port}')
            sys.exit(1)

    def run(self):
        self.running = True

        # Start a thread to get the user input and either process it as a command or send it to the server
        # This is flagged as a daemon thread, so it will terminate when the main thread terminates
        threading.Thread(target=get_and_send, args=(self,), daemon=True).start()

        """ Chat client main loop """
        while self.running:
            # Print the prompt
            sys.stdout.write(self.prompt)
            sys.stdout.flush()

            # Wait for data from the server through the socket
            try:
                readable, writeable, exceptional = select.select([self.sock], [], [])
            except select.error as e:
                print('Error: ', e)
                break

            for sock in readable:
                # Read data only if it is from the server
                if sock == self.sock:
                    try:
                        data = receive(self.sock)
                        # If no data, server has closed the connection
                        if not data:
                            print('Client shutting down.')
                            self.running = False
                        # Else print the data as it is a message from the server
                        else:
                            sys.stdout.write(data + '\n')
                            sys.stdout.flush()
                    except socket.error as e:
                        print('Error: ', e)
                        print('Shutting down.')
                        self.running = False
        # Cleanup the connection after the main loop
        self.sock.close()
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', action="store",
                        dest="port", type=int, required=True)
    given_args = parser.parse_args()

    port = given_args.port

    client = ChatClient(port=port)

    client.run()