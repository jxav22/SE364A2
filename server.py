import socket
import threading
import sys
import argparse
import json
import os
import pickle

host = "localhost"
data_payload = 2048
backlog = 1


def dumb_chat_server(port):
    """A dumb chat server"""
    # Create a TCP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Enable reuse address/port
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    # Bind the socket to the port
    print(f"Starting up chat server on {host} port {port}")
    sock.bind((host, port))

    # Listen to clients, backlog argument specifies the max no.of queued connections
    sock.listen(backlog)

    print("Waiting a client")
    client, address = sock.accept()

    while True:
        print("Waiting a client's message")
        data = client.recv(data_payload)
        if data:
            print(f"client> {json.loads(data.decode())}")

        message = input("> ")
        client.send(message.encode("utf-8"))

    # end connection
    client.close()


class UserData:
    def __init__(self, username, password):
        self.username = username
        self.password = password


class UserDataRepository:
    file_path = "./user_data.pkl"

    def __init__(self):
        self.users_data = self.load_data()

    def load_data(self):
        if os.path.exists(self.file_path):
            with open(self.file_path, "rb") as file:
                try:
                    data = pickle.load(file)
                except (pickle.UnpicklingError, EOFError):
                    data = {}
        else:
            data = {}
        return data

    def save_data(self):
        with open(self.file_path, "wb") as file:
            pickle.dump(self.users_data, file)

    def create_user(self, username, password):
        if username not in self.users_data:
            self.users_data[username] = UserData(username, password)
            self.save_data()
            return True
        return False

    def validate_user(self, username, password):
        return any(
            user.username == username and user.password == password
            for user in self.users_data.values()
        )


class AuthManager:
    def __init__(self, current_user_data):
        self.user_data_repository = UserDataRepository()
        self.user_data = current_user_data

    def login(self, username, password):
        response = self.user_data_repository.validate_user(username, password)
        if response:
            user_data = self.current_user_data.get()
            user_data.display_name = username
            self.current_user_data.set(user_data)
        return response

    def register(self, username, password):
        return self.user_data_repository.create_user(username, password)

    def check_auth(self, username, password):
        return self.user_data_repository.validate_user(username, password)


class Command:
    def __init__(self, socket):
        self.socket = socket

    def respond(self, data):
        self.socket.sendall(json.dumps(data).encode("utf-8"))

    def execute(self):
        pass


class LoginCommand(Command):
    def __init__(self, socket, data, auth_manager):
        super().__init__(socket)
        self.data = data
        self.auth_manager = auth_manager

    def execute(self):
        print("LOGGING IN")
        login_successful = self.auth_manager.login(
            self.data["username"], self.data["password"]
        )

        if login_successful:
            self.respond({"status": "success"})
        else:
            self.respond(
                {"status": "failure", "message": "Invalid username or password"}
            )


class RegisterCommand(Command):
    def __init__(self, socket, data, auth_manager):
        super().__init__(socket)
        self.data = data
        self.auth_manager = auth_manager

    def execute(self):
        print("REGISTERING")
        register_successful = self.auth_manager.register(
            self.data["username"], self.data["password"]
        )

        if register_successful:
            self.respond({"status": "success"})
        else:
            self.respond(
                {"status": "failure", "message": "Invalid username or password"}
            )


class AuthCommand(Command):
    def __init__(self, socket, data, auth_manager):
        super().__init__(socket)
        self.data = data
        self.auth_manager = auth_manager

    def execute(self):
        username = self.data["username"]
        password = self.data["password"]

        if self.auth_manager.check_auth(username, password):
            return True
        else:
            self.respond({"status": "failure", "message": "Not authorized"})
            return False


class AdvertiseCommand(AuthCommand):
    def __init__(self, socket, data, auth_manager, user_data, current_user_data):
        super().__init__(socket, data, auth_manager)
        self.user_data = user_data
        self.current_user_data = current_user_data

    def execute(self):
        if super().execute():
            user_data = self.current_user_data.get()
            user_data.available = True
            self.current_user_data.set(user_data)

            users = self.user_data.get_users()
            available_users = [user.display_name for user in users if user.available and user.display_name != user_data.display_name]

            self.respond({"status": "success", "users": available_users})

class ConnectCommand(AuthCommand):
    def __init__(self, socket, data, auth_manager, user_data):
        super().__init__(socket, data, auth_manager)
        self.user_data = user_data
    
    def execute(self):
        if super().execute():
            partner = self.data["target"]

            current_user_data = self.user_data.get_current_user_data()
            current_user_data.partner = partner
            self.user_data.set_current_user_data(current_user_data)

            partner_user_data = next(user for user in self.user_data.get_users() if user.display_name == partner)
            partner_user_data.partner = current_user_data.display_name
            self.user_data.set_data(partner_user_data)

            self.respond({"status": "success"})

class CommandFactory:
    @staticmethod
    def create_command(data, socket, auth_manager, user_data, current_user_data):
        command = data["command"]

        if command == "login":
            return LoginCommand(socket, data, auth_manager)
        elif command == "register":
            return RegisterCommand(socket, data, auth_manager)
        elif command == "advertise":
            return AdvertiseCommand(socket, data, auth_manager, user_data, current_user_data)
        else:
            return None


class UserInfo:
    data = {}

    def __init__(self, socket):
        self.data["socket"] = socket
        self.data["display_name"] = None
        self.data["partner"] = None
        self.data["available"] = False


class UserInfoManager:
    def __init__(self):
        self.user_data = {}

    def get_data(self, id):
        return self.user_data[id]

    def set_data(self, id, data):
        self.user_data[id] = data

    def get_users(self):
        return self.user_data.values()
    
class CurrentUserInfo(UserInfoManager):
    def __init__(self):
        super().__init__()

    def get_current_thread_id(self):
        return threading.current_thread().ident
    
    def get(self):
        return super().get_data(self.get_current_thread_id())
    
    def set(self, data):
        super().set_data(self.get_current_thread_id(), data)


class Server:
    data_payload = 2048
    backlog = 5

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))

        self.connections = []
        self.user_data = UserInfoManager()
        self.current_user_data = CurrentUserInfo()
        self.auth_manager = AuthManager(self.user_data)

    def handle_client(self, client_socket, address):
        print(f"Accepted connection from {address}")

        self.user_data.set_current_user_data(UserInfo(client_socket))

        # Handle client communication here
        # For example, you can use client_socket.recv() to receive data from the client
        # and client_socket.send() to send data to the client
        while True:
            data = json.loads(client_socket.recv(data_payload).decode())
            if data["command"] == "close":
                break
            else:
                command = CommandFactory.create_command(
                    data, client_socket, self.auth_manager, self.user_data, self.current_user_data
                )
                command.execute()

        client_socket.close()
        print(f"Connection from {address} closed")

    def start(self):
        self.server_socket.listen(self.backlog)
        print(f"Server listening on {self.host}:{self.port}...")

        while True:
            client_socket, client_address = self.server_socket.accept()
            client_thread = threading.Thread(
                target=self.handle_client, args=(client_socket, client_address)
            )
            client_thread.start()
            self.connections.append(client_thread)


if __name__ == "__main__":
    server = Server("localhost", 20)  # Change the IP address and port as needed
    server.start()


# if __name__ == '__main__':
#     parser = argparse.ArgumentParser(description='Socket Server Example')
#     parser.add_argument('--port', action="store",
#                         dest="port", type=int, required=True)
#     given_args = parser.parse_args()
#     port = given_args.port
#     dumb_chat_server(port)
