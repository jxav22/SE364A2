import socket
import threading
from threading import Event
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


class Credentials:
    def __init__(self, username, password):
        self.username = username
        self.password = password


class CredentialsRepository:
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
            self.users_data[username] = Credentials(username, password)
            self.save_data()
            return True
        return False

    def user_exists(self, username, password):
        return any(
            user.username == username and user.password == password
            for user in self.users_data.values()
        )

    def username_exists(self, username):
        return any(user.username == username for user in self.users_data.values())


class AuthManager:
    def __init__(self, user_data, user_data_manager):
        self.credentials_repository = CredentialsRepository()
        self.user_data = user_data
        self.user_data_manager = user_data_manager

    def login(self, username, password):
        user_exists = self.credentials_repository.user_exists(username, password)
        user_logged_in = self.user_data_manager.is_logged_in(username)

        if user_logged_in:
            return {"status": "failure", "message": "User is already logged in"}

        can_log_in = user_exists and not user_logged_in

        if can_log_in:
            self.user_data.logged_in = True
            self.user_data.display_name = username
            return {"status": "success"}

        return {"status": "failure", "message": "Invalid credentials"}

    def register(self, username, password):
        return self.credentials_repository.create_user(username, password)

    def authorize(self, username, password):
        return self.credentials_repository.user_exists(username, password)

    def username_exists(self, username):
        return self.credentials_repository.username_exists(username)


class Command:
    def __init__(self, socket, data):
        self.data = data
        self.socket = socket

    def respond(self, data):
        data["ID"] = self.data["ID"]
        self.socket.sendall(json.dumps(data).encode("utf-8"))

    def execute(self):
        pass


class LoginCommand(Command):
    def __init__(self, socket, data, auth_manager):
        super().__init__(socket, data)
        self.data = data
        self.auth_manager = auth_manager

    def execute(self):
        self.respond(
            self.auth_manager.login(self.data["username"], self.data["password"])
        )


class RegisterCommand(Command):
    def __init__(self, socket, data, auth_manager):
        super().__init__(socket, data)
        self.data = data
        self.auth_manager = auth_manager

    def execute(self):
        register_successful = self.auth_manager.register(
            self.data["username"], self.data["password"]
        )

        if register_successful:
            self.respond({"status": "success"})
        elif self.auth_manager.username_exists(self.data["username"]):
            self.respond({"status": "failure", "message": "Account already exists"})
        else:
            self.respond(
                {"status": "failure", "message": "Something went wrong. Try again"}
            )


class AuthCommand(Command):
    def __init__(self, socket, data, auth_manager):
        super().__init__(socket, data)
        self.data = data
        self.auth_manager = auth_manager

    def execute(self):
        username = self.data["username"]
        password = self.data["password"]

        if self.auth_manager.authorize(username, password):
            return True
        else:
            self.respond(
                {"status": "failure", "message": "Error - authorization required"}
            )
            return False


class AdvertiseCommand(AuthCommand):
    def __init__(self, socket, data, auth_manager, user_data_manager, user_data):
        super().__init__(socket, data, auth_manager)
        self.user_data_manager = user_data_manager
        self.user_data = user_data

    def execute(self):
        if super().execute():
            users = self.user_data_manager.get_users()
            available_users = [
                user.display_name
                for user in users
                if user.display_name != self.user_data.display_name
            ]

            self.respond({"status": "success", "users": available_users})


class ConnectCommand(AuthCommand):
    timeout = 60

    def __init__(self, socket, data, auth_manager, user_data_manager, user_data):
        super().__init__(socket, data, auth_manager)
        self.user_data_manager = user_data_manager
        self.data = data
        self.user_data = user_data

    def execute(self):
        if super().execute():
            target = self.data["target"]
            self.user_data.target = target

            target_data = self.user_data_manager.get_user(target)

            if target_data.target == self.user_data.display_name:
                self.respond({"status": "success", "username": self.user_data.display_name, "address": self.user_data.address, "port":self.user_data.port, "is_client": True})
                self.user_data.partner = target
                self.user_data.available.set()
            elif target_data.available.wait(self.timeout):
                self.user_data.partner = target
                self.respond({"status": "success", "username": self.user_data.display_name, "address":"", "port": target_data.port, "is_client": False})
            else:
                self.respond({"status": "failure", "message": "User not available"})
            self.user_data.target = None


class MessageCommand(AuthCommand):
    def __init__(self, socket, data, auth_manager, user_data_manager, user_data):
        super().__init__(socket, data, auth_manager)
        self.user_data_manager = user_data_manager
        self.data = data
        self.user_data = user_data

    def relay_message(self, socket, message):
        message_contents = {
            "command": "message",
            "username": self.user_data.display_name,
            "message": message,
        }
        socket.sendall(json.dumps(message_contents).encode("utf-8"))

    def system_message(self, socket, message):
        message_contents = {
            "command": "message",
            "username": "",
            "message": message,
        }
        socket.sendall(json.dumps(message_contents).encode("utf-8"))

    def execute(self):
        if super().execute():
            partner_data = self.user_data_manager.get_user(self.user_data.partner)

            if self.data.get("quit", False):
                self.user_data.partner = None
                partner_data.partner = None
                self.system_message(partner_data.socket, "LMAO THEY QUIT")
                self.respond({"status": "failure", "message": "no partner"})
            elif self.user_data.partner is None:
                self.respond({"status": "failure", "message": "No partner"})
            else:
                self.relay_message(partner_data.socket, self.data["message"])
                self.respond({"status": "success"})


class CommandFactory:
    @staticmethod
    def create_command(data, socket, user_data_manager, auth_manager, user_data):
        print(data)
        command = data["command"]

        if command == "login":
            return LoginCommand(socket, data, auth_manager)
        elif command == "register":
            return RegisterCommand(socket, data, auth_manager)
        elif command == "advertise":
            return AdvertiseCommand(
                socket, data, auth_manager, user_data_manager, user_data
            )
        elif command == "connect":
            return ConnectCommand(
                socket, data, auth_manager, user_data_manager, user_data
            )
        elif command == "message":
            return MessageCommand(
                socket, data, auth_manager, user_data_manager, user_data
            )
        else:
            return None


class UserData:
    def __init__(self, socket, address, port):
        self.socket = socket
        self.display_name = None
        self.target = None
        self.partner = None
        self.available = Event()
        self.logged_in = True
        self.address = address
        self.port = port


class UserDataManager:
    def __init__(self):
        self.user_data = []

    def add_user_data(self, user_data):
        self.user_data.append(user_data)

    def get_users(self):
        return self.user_data

    def get_user(self, username):
        return next(user for user in self.user_data if user.display_name == username)

    def delete_user(self, user_data):
        self.user_data.remove(user_data)

    def is_logged_in(self, username):
        return any(
            user.display_name == username and user.logged_in for user in self.user_data
        )


class Server:
    data_payload = 2048
    backlog = 5

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.connections = []
        self.user_data_manager = UserDataManager()

    def close_client(self, client_socket, user_data, address):
        client_socket.close()
        print(f"Connection from {address} closed")
        self.user_data_manager.delete_user(user_data)

    def handle_client(self, client_socket, address):
        user_data = UserData(client_socket, address[0], address[1])
        auth_manager = AuthManager(user_data, self.user_data_manager)

        self.user_data_manager.add_user_data(user_data)

        print(f"Accepted connection from {address}")
        # Handle client communication here
        # For example, you can use client_socket.recv() to receive data from the client
        # and client_socket.send() to send data to the client
        try:
            while True:
                data = json.loads(client_socket.recv(data_payload).decode())
                if data["command"] == "close":
                    break
                else:
                    command = CommandFactory.create_command(
                        data,
                        client_socket,
                        self.user_data_manager,
                        auth_manager,
                        user_data,
                    )
                    command.execute()
        except json.JSONDecodeError:
            print("Error: Invalid JSON data received from the client.")
            self.close_client(client_socket, user_data, address)
            # Handle the error or log it as needed
        except KeyError as e:
            print(f"Error: Missing key in received data - {e}")
            self.close_client(client_socket, user_data, address)
            # Handle the error or log it as needed
        except Exception as e:
            print(f"Error: An unexpected error occurred - {e}")
            self.close_client(client_socket, user_data, address)

    def start(self):
        self.server_socket.bind((self.host, self.port))
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
