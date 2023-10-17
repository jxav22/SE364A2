import socket
import json
import threading


class ContextSwitcher:
    def __init__(self, host, address, username, is_client):
        self.client_server = ClientServer(host, address)
        if is_client:
            self.client_server.start_as_client()
        else:
            self.client_server.start_as_server()

        self.client_server_controller = ClientServerController(self.client_server, username)
        self.message_view = MessageView(self.client_server_controller)

        self.message_view.activate()


class MessageView:
    def __init__(self, client_server_controller):
        self.client_server_controller = client_server_controller

    def activate(self):
        while True:
            message = input("")

            if message == "quit":
                response = self.client_server_controller.quit()
                if response["status"] == "failure":
                    print(response["message"])
                else:
                    self.client_server_controller.close()
                    break

            response = self.client_server_controller.send(message)
            if response["status"] == "failure":
                print(response["message"])


class ClientServerController:
    def __init__(self, client_server, username):
        self.username = username
        self.client_server = client_server
        self.request_helper = RequestHelper(client_server)

    def send(self, message):
        return self.request_helper.request({"command": "message", "username": self.username, "message": message})
    
    def quit(self):
        return self.request_helper.request({"command": "quit"})
    
    def close(self):
        self.request_helper.stop()
        self.client_server.close()


class Command:
    def __init__(self, client_server, data):
        self.data = data
        self.client_server = client_server

    def respond(self, data):
        data["ID"] = self.data["ID"]
        self.client_server.send(data)

    def execute(self):
        pass


class MessageCommand(Command):
    def __init__(self, client_server, data):
        super().__init__(client_server, data)
        self.data = data

    def execute(self):
        print(f"{self.data['username']}: {self.data['message']}")
        self.respond({"status": "success"})


class QuitCommand(Command):
    def __init__(self, client_server, data, request_helper):
        super().__init__(client_server, data)
        self.data = data
        self.request_helper = request_helper

    def execute(self):
        self.respond({"status": "success"})
        self.request_helper.stop()
        self.client_server.close()


class CommandFactory:
    @staticmethod
    def create_command(data, client_server, request_helper):
        command = data["command"]

        if command == "message":
            return MessageCommand(client_server, data)
        elif command == "quit":
            return QuitCommand(client_server, data, request_helper)
        else:
            return None


class RequestHelper:
    timeout = 60
    id = 0

    def __init__(self, client_server):
        self.client_server = client_server
        self.event_pool = {}

        self.stop_event = threading.Event()
        threading.Thread(target=self.listen).start()

    def request(self, data):
        self.id += 1
        data["ID"] = self.id
        self.client_server.send(data)

        self.event_pool[self.id] = threading.Event()
        flag = self.event_pool[self.id].wait(self.timeout)

        if flag:
            response = self.event_pool[self.id]
            del self.event_pool[self.id]
            return response
        else:
            return {"status": "failure", "message": "Request timed out"}

    def listen(self):
        while not self.stop_event.is_set():
            response = self.client_server.receive()

            if response.get("ID") in self.event_pool:
                event = self.event_pool[response["ID"]]
                self.event_pool[response["ID"]] = response
                event.set()
            elif response.get("command"):
                CommandFactory.create_command(response, self.client_server, self).execute()


    def stop(self):
        self.stop_event.set()


class ClientServer:
    buffer_size = 2048

    def __init__(self, host, port):
        self.host = host
        self.port = port

        # Create a TCP/IP socket
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.client_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def start_as_client(self):
        # Connect the socket to the server
        self.client_socket.connect((self.host, self.port))
        print(f"Client started on {self.host}:{self.port}...")

    def start_as_server(self):
        # Bind the socket to the port
        self.client_socket.bind((self.host, self.port))
        print(f"Server started on {self.host}:{self.port}...")

        # Listen for incoming connections
        self.client_socket.listen(1)

        # Wait for a connection
        print("Waiting for a connection...")
        self.client_socket, self.client_address = self.client_socket.accept()
        print(f"Connected to {self.client_address}")

    def process_before_sending(self, data):
        return json.dumps(data).encode("utf-8")

    def process_received(self, data):
        return json.loads(data.decode())

    def send(self, data):
        try:
            self.client_socket.send(self.process_before_sending(data))
        except socket.error as e:
            print(f"Socket error: {str(e)}")
        except Exception as e:
            print(f"Other exception: {str(e)}")

    def receive(self):
        try:
            response_data = self.client_socket.recv(self.buffer_size)
            return self.process_received(response_data)
        except Exception as e:
            print(f"Other exception: {str(e)}")
            return {"status": "failure", "message": "Error receiving data"}

    def close(self):
        print("Closing connection to the server")
        self.client_socket.close()

if __name__ == "__main__":
    ContextSwitcher("localhost", 20, "Cob", False)  # Change the IP address and port as needed
